"""FalkorDB graph adapter layer.

This is the ONLY module in the entire codebase that imports falkordb or redis.
"""

from typing import Any, Dict, List, Optional
import falkordb
from falkordb import FalkorDB, Graph
from graph_intelligence.common.config import get_settings
from graph_intelligence.common.errors import DatabaseUnavailable
from graph_intelligence.common.logging_setup import get_logger
from graph_intelligence.common.schema import ALL_LABELS

logger = get_logger("falkordb_client")

_falkordb_client: Optional[FalkorDB] = None


def get_falkordb_connection() -> FalkorDB:
    """Lazy singleton FalkorDB connection."""
    global _falkordb_client
    if _falkordb_client is None:
        settings = get_settings()
        pwd = settings.get_password_str()
        try:
            _falkordb_client = FalkorDB(
                host=settings.FALKORDB_HOST,
                port=settings.FALKORDB_PORT,
                username=settings.FALKORDB_USERNAME,
                password=pwd,
                ssl=settings.FALKORDB_SSL,
                socket_timeout=15,
                socket_connect_timeout=15,
            )
        except Exception as exc:
            err_str = str(exc).lower()
            if "without any password configured" in err_str:
                logger.warning(
                    "FalkorDB instance has no password configured on default user. "
                    "Retrying connection without password (password=None, username=None)..."
                )
                try:
                    _falkordb_client = FalkorDB(
                        host=settings.FALKORDB_HOST,
                        port=settings.FALKORDB_PORT,
                        username=None,
                        password=None,
                        ssl=settings.FALKORDB_SSL,
                        socket_timeout=15,
                        socket_connect_timeout=15,
                    )
                    logger.info("FalkorDB connection successfully established without password.")
                    return _falkordb_client
                except Exception as inner_exc:
                    raise DatabaseUnavailable(f"Failed to initialize FalkorDB client: {str(inner_exc)}") from inner_exc

            if settings.FALKORDB_USERNAME and ("invalid username-password pair" in err_str or "wrongpass" in err_str):
                logger.warning(
                    f"FalkorDB authentication failed with username='{settings.FALKORDB_USERNAME}'. "
                    "Falling back to default user (username=None) for standalone Redis/FalkorDB with --requirepass..."
                )
                try:
                    _falkordb_client = FalkorDB(
                        host=settings.FALKORDB_HOST,
                        port=settings.FALKORDB_PORT,
                        username=None,
                        password=pwd,
                        ssl=settings.FALKORDB_SSL,
                        socket_timeout=15,
                        socket_connect_timeout=15,
                    )
                    logger.info("FalkorDB connection successfully established using default user.")
                    return _falkordb_client
                except Exception as inner_exc:
                    raise DatabaseUnavailable(f"Failed to initialize FalkorDB client: {str(inner_exc)}") from inner_exc
            raise DatabaseUnavailable(f"Failed to initialize FalkorDB client: {str(exc)}") from exc
    return _falkordb_client


class GraphStore:
    """Scoped access layer for a named FalkorDB graph."""

    def __init__(self, graph_name: Optional[str] = None):
        settings = get_settings()
        self.graph_name = graph_name or settings.FALKORDB_GRAPH
        self._graph: Optional[Graph] = None

    @property
    def graph(self) -> Graph:
        if self._graph is None:
            client = get_falkordb_connection()
            try:
                self._graph = client.select_graph(self.graph_name)
            except Exception as exc:
                raise DatabaseUnavailable(f"Failed to select graph '{self.graph_name}': {str(exc)}") from exc
        return self._graph

    def query(self, cypher: str, params: Optional[Dict[str, Any]] = None, retry_count: int = 1) -> List[Dict[str, Any]]:
        """
        Execute a Cypher query with parameters.
        Returns a list of dictionaries mapping column headers to row values.
        Wraps driver connection/query failures into DatabaseUnavailable.
        """
        last_exception: Optional[Exception] = None
        for attempt in range(retry_count + 1):
            try:
                result = self.graph.query(cypher, params=params or {})
                headers = []
                for h in (result.header or []):
                    col = h[1] if isinstance(h, (list, tuple)) and len(h) > 1 else h
                    if isinstance(col, bytes):
                        col = col.decode("utf-8")
                    headers.append(str(col))
                rows = []
                for row in (result.result_set or []):
                    row_dict = {}
                    for idx, col in enumerate(headers):
                        val = row[idx] if idx < len(row) else None
                        row_dict[col] = val
                    rows.append(row_dict)
                return rows
            except DatabaseUnavailable:
                raise
            except Exception as exc:
                last_exception = exc
                err_msg = str(exc)
                logger.warning(f"Query attempt {attempt + 1} failed on graph {self.graph_name}: {err_msg}")
                # Only reset connection on actual connection or timeout errors, not Cypher syntax or indexing errors
                if "connection" in err_msg.lower() or "timeout" in err_msg.lower() or "socket" in err_msg.lower():
                    self._graph = None

        raise DatabaseUnavailable(f"Database query failed on '{self.graph_name}': {str(last_exception)}") from last_exception

    def ping(self) -> bool:
        """Verify DB connection by executing RETURN 1."""
        try:
            res = self.query("RETURN 1 AS ping")
            return len(res) > 0 and res[0].get("ping") == 1
        except Exception:
            return False

    def ensure_indexes(self) -> None:
        """Create indexes on id for all schema labels, plus SessionSummary user_id and status."""
        existing_indexes = set()
        try:
            idx_res = self.graph.query("CALL db.indexes()")
            for row in (idx_res.result_set or []):
                if len(row) >= 2:
                    lbl = row[0]
                    fields = row[1] if isinstance(row[1], (list, tuple)) else [row[1]]
                    for f in fields:
                        existing_indexes.add((lbl, f))
        except Exception as exc:
            logger.debug(f"Could not inspect db.indexes: {exc}")

        for label in sorted(ALL_LABELS):
            if (label, "id") in existing_indexes:
                continue
            index_cypher = f"CREATE INDEX FOR (n:{label}) ON (n.id)"
            try:
                self.graph.query(index_cypher)
            except Exception as exc:
                if "already indexed" not in str(exc).lower():
                    logger.debug(f"Index creation note for {label}(id): {exc}")

        # Memory specific indexes
        for field in ["user_id", "status"]:
            if ("SessionSummary", field) in existing_indexes:
                continue
            index_cypher = f"CREATE INDEX FOR (n:SessionSummary) ON (n.{field})"
            try:
                self.graph.query(index_cypher)
            except Exception as exc:
                if "already indexed" not in str(exc).lower():
                    logger.debug(f"Index creation note for SessionSummary({field}): {exc}")

    def delete_graph(self) -> None:
        """Delete or clear the graph."""
        try:
            self.graph.delete()
        except Exception:
            try:
                self.query("MATCH (n) DETACH DELETE n")
            except Exception as exc:
                raise DatabaseUnavailable(f"Failed to clear graph '{self.graph_name}': {str(exc)}") from exc
