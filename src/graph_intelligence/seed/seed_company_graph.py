"""Idempotent seed loader for GraphCortex enterprise knowledge graph."""

import json
from pathlib import Path
from typing import Dict, Any, List
from graph_intelligence.common.falkordb_client import GraphStore
from graph_intelligence.common.ids import utcnow_iso
from graph_intelligence.common.logging_setup import get_logger

logger = get_logger("seed_company_graph")

DATA_PATH = Path(__file__).resolve().parent / "demo_data.json"


def load_demo_data() -> Dict[str, Any]:
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def seed_company_graph(graph_name: str | None = None) -> Dict[str, int]:
    """
    Seed the graph idempotently with company nodes, relationships, and user identity nodes.
    Returns counts of seeded entities.
    """
    data = load_demo_data()
    store = GraphStore(graph_name=graph_name)
    now = utcnow_iso()

    # Step 1: Ensure indexes
    store.ensure_indexes()

    # Step 2: Seed company nodes
    nodes_created_or_updated = 0
    for node in data.get("company_nodes", []):
        label = node["label"]
        node_id = node["id"]
        name = node["name"]
        aliases = node.get("aliases", [])
        code = node.get("code")
        props = node.get("properties", {})

        # Prepare parameters
        cypher = f"""
        MERGE (n:{label} {{id: $id}})
        ON CREATE SET
            n.name = $name,
            n.aliases = $aliases,
            n.code = $code,
            n.source = 'seed',
            n.created_at = $now,
            n.updated_at = $now
        ON MATCH SET
            n.name = $name,
            n.aliases = $aliases,
            n.code = $code,
            n.updated_at = $now
        """
        params: Dict[str, Any] = {
            "id": node_id,
            "name": name,
            "aliases": aliases,
            "code": code,
            "now": now,
        }

        # Dynamic property setting
        for k, v in props.items():
            param_key = f"prop_{k}"
            cypher += f"\nSET n.{k} = ${param_key}"
            params[param_key] = v

        cypher += "\nRETURN n.id AS id"
        store.query(cypher, params)
        nodes_created_or_updated += 1

    # Step 3: Seed user identity nodes
    users_seeded = 0
    for user in data.get("user_nodes", []):
        user_id = user["id"]
        name = user["name"]
        props = user.get("properties", {})
        cypher = """
        MERGE (u:User {id: $id})
        ON CREATE SET
            u.name = $name,
            u.source = 'seed',
            u.created_at = $now,
            u.updated_at = $now
        ON MATCH SET
            u.name = $name,
            u.updated_at = $now
        RETURN u.id AS id
        """
        store.query(cypher, {"id": user_id, "name": name, "now": now})
        users_seeded += 1

    # Step 4: Seed relationships
    edges_seeded = 0
    for rel in data.get("relationships", []):
        rel_type = rel["type"]
        from_id = rel["from_id"]
        to_id = rel["to_id"]

        cypher = f"""
        MATCH (a {{id: $from_id}})
        MATCH (b {{id: $to_id}})
        MERGE (a)-[r:{rel_type}]->(b)
        ON CREATE SET r.source = 'seed', r.created_at = $now
        RETURN type(r) AS rel_type
        """
        store.query(cypher, {"from_id": from_id, "to_id": to_id, "now": now})
        edges_seeded += 1

    return {
        "company_nodes": nodes_created_or_updated,
        "user_nodes": users_seeded,
        "relationships": edges_seeded,
    }
