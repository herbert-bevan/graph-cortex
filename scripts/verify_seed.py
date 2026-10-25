"""Verification script for GraphCortex seed data integrity."""

import sys
from graph_intelligence.common.config import get_settings
from graph_intelligence.common.falkordb_client import GraphStore

def verify_seed(graph_name: str | None = None) -> bool:
    settings = get_settings()
    target_graph = graph_name or settings.FALKORDB_GRAPH
    print(f"Verifying graph '{target_graph}'...")
    store = GraphStore(graph_name=target_graph)

    # 1. Check company nodes count (labels: Company, Team, Person, Project, Service, Feature, Incident, Decision, Document)
    node_query = """
    MATCH (n)
    WHERE any(label IN labels(n) WHERE label IN [
        'Company', 'Team', 'Person', 'Project', 'Service', 'Feature', 'Incident', 'Decision', 'Document'
    ])
    RETURN count(DISTINCT n) AS company_node_count
    """
    res = store.query(node_query)
    company_node_count = res[0]["company_node_count"]
    print(f"- Company nodes: {company_node_count} (expected: 31)")
    assert company_node_count == 31, f"Expected 31 company nodes, got {company_node_count}"

    # 2. Check relationship count among company nodes
    edge_query = """
    MATCH (a)-[r]->(b)
    WHERE any(label IN labels(a) WHERE label IN ['Company', 'Team', 'Person', 'Project', 'Service', 'Feature', 'Incident', 'Decision', 'Document'])
      AND any(label IN labels(b) WHERE label IN ['Company', 'Team', 'Person', 'Project', 'Service', 'Feature', 'Incident', 'Decision', 'Document'])
    RETURN count(r) AS rel_count
    """
    res = store.query(edge_query)
    rel_count = res[0]["rel_count"]
    print(f"- Company relationships: {rel_count} (expected: 53)")
    assert rel_count == 53, f"Expected 53 relationships, got {rel_count}"

    # 3. Check User nodes count
    user_query = "MATCH (u:User) RETURN count(u) AS user_count"
    res = store.query(user_query)
    user_count = res[0]["user_count"]
    print(f"- User identity nodes: {user_count} (expected: 2)")
    assert user_count == 2, f"Expected 2 User nodes, got {user_count}"

    # 4. Check SessionSummary nodes count (must be 0 on fresh seed)
    summary_query = "MATCH (s:SessionSummary) RETURN count(s) AS summary_count"
    res = store.query(summary_query)
    summary_count = res[0]["summary_count"]
    print(f"- SessionSummary nodes: {summary_count} (expected: 0)")
    assert summary_count == 0, f"Expected 0 SessionSummary nodes on fresh seed, got {summary_count}"

    # 5. Spot-query: owner of svc-payment is Maya Chen (team Payments)
    owner_query = """
    MATCH (p:Person)-[:OWNS]->(s:Service {id: 'svc-payment'})
    MATCH (p)-[:MEMBER_OF]->(t:Team)
    RETURN p.name AS person_name, t.name AS team_name
    """
    res = store.query(owner_query)
    assert len(res) == 1, "Owner query returned no results"
    assert res[0]["person_name"] == "Maya Chen", f"Expected Maya Chen, got {res[0]['person_name']}"
    assert res[0]["team_name"] == "Payments", f"Expected Payments team, got {res[0]['team_name']}"
    print(f"- Spot-query 1 passed: svc-payment owned by {res[0]['person_name']} ({res[0]['team_name']})")

    # 6. Spot-query: adr-014 SUPPORTED_BY doc-adr-014
    doc_query = """
    MATCH (d:Decision {id: 'adr-014'})-[:SUPPORTED_BY]->(doc:Document {id: 'doc-adr-014'})
    RETURN d.name AS decision, doc.name AS document
    """
    res = store.query(doc_query)
    assert len(res) == 1, "Decision doc query returned no results"
    print(f"- Spot-query 2 passed: {res[0]['decision']} supported by {res[0]['document']}")

    print("\nGraph verification PASSED with 100% integrity!")
    return True

if __name__ == "__main__":
    try:
        verify_seed()
    except Exception as exc:
        print(f"Verification failed: {exc}", file=sys.stderr)
        sys.exit(1)
