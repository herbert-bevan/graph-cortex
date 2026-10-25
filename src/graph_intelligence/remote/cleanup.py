"""Daily cleanup job for stale guest records, session logs, and dead FalkorDB graphs/nodes."""

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
import os

from graph_intelligence.common.config import get_settings
from graph_intelligence.common.logging_setup import get_logger
from graph_intelligence.remote.auth import _get_connection, _USE_POSTGRES

logger = get_logger("cleanup_service")


def cleanup_stale_records_and_graphs(days: int = 2) -> Dict[str, Any]:
    """Purge DB guest records, session logs, and user memory graph nodes older than `days` days.

    Also identifies and cleans up dead temporary test/demo graphs in FalkorDB.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    cutoff_iso = cutoff.isoformat()

    results: Dict[str, Any] = {
        "cutoff": cutoff_iso,
        "deleted_guest_ids": [],
        "deleted_guest_count": 0,
        "deleted_session_logs_count": 0,
        "falkordb_cleaned_nodes": 0,
        "deleted_dead_graphs": [],
        "errors": [],
    }

    # -----------------------------------------------------------------------
    # 1. Clean Database Records (Postgres / SQLite)
    # -----------------------------------------------------------------------
    stale_guest_ids: List[str] = []
    try:
        conn = _get_connection()
        try:
            cur = conn.cursor()
            if _USE_POSTGRES:
                cur.execute(
                    "SELECT id FROM guest_users WHERE created_at < %s OR expires_at < %s",
                    (cutoff, cutoff),
                )
            else:
                cur.execute(
                    "SELECT id FROM guest_users WHERE created_at < ? OR expires_at < ?",
                    (cutoff_iso, cutoff_iso),
                )
            rows = cur.fetchall()
            if _USE_POSTGRES:
                stale_guest_ids = [r[0] for r in rows]
            else:
                stale_guest_ids = [r["id"] if hasattr(r, "keys") else r[0] for r in rows]

            if stale_guest_ids:
                # Delete session logs for these guests or logs older than cutoff
                if _USE_POSTGRES:
                    cur.execute(
                        "DELETE FROM guest_session_logs WHERE guest_id = ANY(%s) OR created_at < %s",
                        (stale_guest_ids, cutoff),
                    )
                    logs_deleted = cur.rowcount if hasattr(cur, "rowcount") else 0
                    cur.execute("DELETE FROM guest_users WHERE id = ANY(%s)", (stale_guest_ids,))
                    guests_deleted = cur.rowcount if hasattr(cur, "rowcount") else len(stale_guest_ids)
                else:
                    placeholders = ",".join("?" for _ in stale_guest_ids)
                    cur.execute(
                        f"DELETE FROM guest_session_logs WHERE guest_id IN ({placeholders}) OR created_at < ?",
                        (*stale_guest_ids, cutoff_iso),
                    )
                    logs_deleted = cur.rowcount if hasattr(cur, "rowcount") else 0
                    cur.execute(
                        f"DELETE FROM guest_users WHERE id IN ({placeholders})",
                        tuple(stale_guest_ids),
                    )
                    guests_deleted = cur.rowcount if hasattr(cur, "rowcount") else len(stale_guest_ids)

                conn.commit()
                results["deleted_guest_ids"] = stale_guest_ids
                results["deleted_guest_count"] = guests_deleted
                results["deleted_session_logs_count"] = logs_deleted
                logger.info(
                    f"Cleaned {guests_deleted} stale guest users and {logs_deleted} logs older than {days} days from database."
                )
            else:
                # Also delete orphan logs older than cutoff even if guest_users row was already gone
                if _USE_POSTGRES:
                    cur.execute("DELETE FROM guest_session_logs WHERE created_at < %s", (cutoff,))
                else:
                    cur.execute("DELETE FROM guest_session_logs WHERE created_at < ?", (cutoff_iso,))
                logs_deleted = cur.rowcount if hasattr(cur, "rowcount") else 0
                conn.commit()
                results["deleted_session_logs_count"] = logs_deleted
        finally:
            conn.close()
    except Exception as exc:
        err_msg = f"Database cleanup error: {exc}"
        logger.warning(err_msg)
        results["errors"].append(err_msg)

    # -----------------------------------------------------------------------
    # 2. Clean FalkorDB Nodes & Dead Graphs
    # -----------------------------------------------------------------------
    try:
        from graph_intelligence.common.falkordb_client import GraphStore, get_falkordb_connection

        store = GraphStore()
        total_nodes_deleted = 0

        # Purge graph nodes for the stale guest IDs
        for gid in stale_guest_ids:
            try:
                # Delete tasks
                store.query("MATCH (t:Task) WHERE t.user_id = $uid DETACH DELETE t", {"uid": gid})
                # Delete session summaries
                store.query("MATCH (s:SessionSummary) WHERE s.user_id = $uid DETACH DELETE s", {"uid": gid})
                # Delete sessions
                store.query("MATCH (ses:Session) WHERE ses.user_id = $uid DETACH DELETE ses", {"uid": gid})
                # Delete user node
                store.query("MATCH (u:User {id: $uid}) DETACH DELETE u", {"uid": gid})
                total_nodes_deleted += 1
            except Exception as e:
                logger.debug(f"Failed to clear graph nodes for guest {gid}: {e}")

        # Purge any remaining orphan guest memories created before cutoff
        try:
            orphan_query = """
            MATCH (s:SessionSummary)
            WHERE s.user_id STARTS WITH 'gst_' AND s.created_at < $cutoff
            OPTIONAL MATCH (s)-[:HAS_TASK]->(t:Task)
            DETACH DELETE s, t
            """
            store.query(orphan_query, {"cutoff": cutoff_iso})
            # Clean orphan User nodes that have no memories left
            store.query("MATCH (u:User) WHERE u.id STARTS WITH 'gst_' AND NOT (u)-[:OWNS_MEMORY]->() DETACH DELETE u")
        except Exception as e:
            logger.debug(f"Note on orphan session summary cleanup: {e}")

        results["falkordb_cleaned_nodes"] = total_nodes_deleted

        # Inspect and delete any dead/temporary test graphs
        try:
            client = get_falkordb_connection()
            settings = get_settings()
            prod_graph = settings.FALKORDB_GRAPH
            if hasattr(client, "list_graphs"):
                available_graphs = client.list_graphs()
                for g_name in available_graphs:
                    # Clean temporary graphs like test_*, temp_*, *_test, *_demo (if not prod)
                    if g_name != prod_graph and (
                        g_name.startswith("temp_")
                        or g_name.startswith("tmp_")
                        or g_name.startswith("test_")
                        or g_name.endswith("_test")
                    ):
                        try:
                            client.select_graph(g_name).delete()
                            results["deleted_dead_graphs"].append(g_name)
                            logger.info(f"Purged dead/temporary FalkorDB graph: {g_name}")
                        except Exception as ge:
                            logger.debug(f"Could not delete dead graph {g_name}: {ge}")
        except Exception as e:
            logger.debug(f"FalkorDB graph listing note: {e}")

    except Exception as exc:
        err_msg = f"FalkorDB cleanup note: {exc}"
        logger.warning(err_msg)
        results["errors"].append(err_msg)

    return results
