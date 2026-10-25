"""Integration tests for persistent session memory."""

import pytest
from graph_intelligence.common.config import get_settings
from graph_intelligence.common.errors import DatabaseUnavailable
from graph_intelligence.common.falkordb_client import GraphStore
from graph_intelligence.memory.service import MemoryService
from graph_intelligence.seed.seed_company_graph import seed_company_graph


@pytest.fixture(scope="module")
def setup_test_graph():
    settings = get_settings()
    test_graph = settings.FALKORDB_GRAPH_TEST
    try:
        seed_company_graph(test_graph)
        store = GraphStore(graph_name=test_graph)
        # Clear existing test summaries
        store.query("MATCH (s:SessionSummary) WHERE s.user_id STARTS WITH 'test-' DETACH DELETE s")
        return test_graph
    except DatabaseUnavailable as exc:
        pytest.skip(f"FalkorDB instance not reachable: {exc}")


def test_full_memory_lifecycle(setup_test_graph):
    test_graph = setup_test_graph
    user_a = "test-user-alice"
    user_b = "test-user-bob"

    service_a = MemoryService(user_id=user_a, graph_name=test_graph)
    service_b = MemoryService(user_id=user_b, graph_name=test_graph)

    # 1. Write Session A summary
    write_res = service_a.remember_session_summary(
        title="Three MCP Services Architecture with FalkorDB",
        summary="We decided to use three Python MCP services over a shared FalkorDB graph. Memory service saves summaries per user and retrieves them in later sessions by topic.",
        keywords=["falkordb", "mcp", "memory", "architecture"],
        entities=["PaymentService"],
        project="Payment Reliability",
        decisions=["Use three separate MCP servers for reasoning, memory, and company brain"],
        open_tasks=["Implement shared core package", "Implement retrieval ranking"],
    )
    assert write_res["ok"] is True
    summary_id_v1 = write_res["summary_id"]
    assert summary_id_v1.startswith("sum_")
    assert write_res["deduplicated"] is False
    assert write_res["status"] == "active"
    assert write_res["summary_version"] == 1

    # 2. Duplicate write -> deduplicated: true
    dup_res = service_a.remember_session_summary(
        title="Three MCP Services Architecture with FalkorDB",
        summary="We decided to use three Python MCP services over a shared FalkorDB graph. Memory service saves summaries per user and retrieves them in later sessions by topic.",
        keywords=["falkordb", "mcp", "memory"],
    )
    assert dup_res["ok"] is True
    assert dup_res["deduplicated"] is True
    assert dup_res["summary_id"] == summary_id_v1

    # 3. Fresh service instance (simulate new process/session B) searches memory
    fresh_service_a = MemoryService(user_id=user_a, graph_name=test_graph)
    search_res = fresh_service_a.search_user_memory(
        query="I'm ready to implement the FalkorDB MCP memory feature. What architecture did we choose, and what were the next steps?",
        keywords=["falkordb", "mcp", "memory"],
        entities=["PaymentService"],
    )
    assert search_res["ok"] is True
    assert search_res["found"] is True
    assert len(search_res["results"]) > 0
    top = search_res["results"][0]
    assert top["summary_id"] == summary_id_v1
    assert top["score"] >= 3.0
    matched_kws = top["matched_keywords"]
    assert "falkordb" in matched_kws
    assert "mcp" in matched_kws
    assert "memory" in matched_kws

    # 4. User isolation: other user (user_b) searches and gets nothing
    search_b = service_b.search_user_memory(
        query="What architecture did we choose for FalkorDB MCP?",
        keywords=["falkordb", "mcp", "memory"],
    )
    assert search_b["ok"] is True
    assert search_b["found"] is False
    assert len(search_b["results"]) == 0

    # User_b cannot update or archive user_a's summary
    update_b = service_b.update_user_memory(
        summary_id=summary_id_v1,
        update_type="append_context",
        reason="Malicious attempt",
    )
    assert update_b["ok"] is False
    assert update_b["error_code"] == "NOT_FOUND"

    # 5. Unrelated query returns found: false
    unrelated_res = fresh_service_a.search_user_memory(
        query="What is the best Italian pasta recipe?",
        keywords=["pasta", "recipe", "dinner"],
    )
    assert unrelated_res["ok"] is True
    assert unrelated_res["found"] is False

    # 6. Update user memory (Session C) -> creates v2, marks v1 superseded
    update_res = fresh_service_a.update_user_memory(
        summary_id=summary_id_v1,
        update_type="append_context",
        updated_summary="The shared core is implemented, and the next task is to test retrieval ranking.",
        complete_tasks=["Implement shared core package"],
        add_open_tasks=["Run smoke test suite"],
        reason="Progress update after completing shared core",
        expected_version=1,
    )
    assert update_res["ok"] is True
    summary_id_v2 = update_res["summary_id"]
    assert summary_id_v2 != summary_id_v1
    assert update_res["summary_version"] == 2
    assert update_res["status"] == "active"

    # Default search returns v2 (v1 is superseded and excluded by default)
    search_v2 = fresh_service_a.search_user_memory(
        query="What is the next task for FalkorDB MCP?",
        keywords=["falkordb", "mcp", "task"],
    )
    assert search_v2["ok"] is True
    assert search_v2["found"] is True
    assert search_v2["results"][0]["summary_id"] == summary_id_v2
    assert search_v2["results"][0]["summary_version"] == 2

    # Search with include_superseded=True returns both
    search_both = fresh_service_a.search_user_memory(
        query="FalkorDB MCP memory architecture",
        keywords=["falkordb", "mcp"],
        include_superseded=True,
    )
    found_ids = {r["summary_id"] for r in search_both["results"]}
    assert summary_id_v2 in found_ids
    assert summary_id_v1 in found_ids

    # 7. Timeline check
    timeline_res = fresh_service_a.get_user_memory_timeline()
    assert timeline_res["ok"] is True
    timeline_ids = [t["summary_id"] for t in timeline_res["timeline"]]
    assert summary_id_v2 in timeline_ids
    assert summary_id_v1 in timeline_ids

    # 8. Status check
    status_res = fresh_service_a.get_memory_status()
    assert status_res["ok"] is True
    assert status_res["configured_user"] == user_a
    assert status_res["active_count"] >= 1
    assert status_res["superseded_count"] >= 1

    # Cleanup
    store = GraphStore(graph_name=test_graph)
    store.query("MATCH (s:SessionSummary) WHERE s.user_id = $uid DETACH DELETE s", {"uid": user_a})
