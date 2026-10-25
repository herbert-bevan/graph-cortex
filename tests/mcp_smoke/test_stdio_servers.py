"""MCP smoke test over real stdio JSON-RPC protocol."""

import os
import sys
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from graph_intelligence.common.config import get_settings
from graph_intelligence.common.errors import DatabaseUnavailable
from graph_intelligence.common.falkordb_client import GraphStore
from graph_intelligence.seed.seed_company_graph import seed_company_graph


@pytest.fixture(scope="module")
def ensure_db():
    settings = get_settings()
    test_graph = settings.FALKORDB_GRAPH_TEST
    try:
        seed_company_graph(test_graph)
        return test_graph
    except DatabaseUnavailable as exc:
        pytest.skip(f"FalkorDB instance not reachable: {exc}")


@pytest.mark.anyio
async def test_reasoning_server_stdio(ensure_db):
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "graph_intelligence.reasoning.mcp_server"],
        env={**os.environ, "FALKORDB_GRAPH": ensure_db},
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools_res = await session.list_tools()
            tool_names = [t.name for t in tools_res.tools]
            assert "find_service_dependencies" in tool_names
            assert "analyze_change_impact" in tool_names
            assert "find_graph_path" in tool_names
            assert "search_connected_entities" in tool_names

            # Test analyze_change_impact
            call_res = await session.call_tool(
                "analyze_change_impact",
                arguments={"target": "PaymentService", "target_type": "Service"},
            )
            assert not call_res.isError
            content = call_res.content[0].text
            assert "PaymentService" in content
            assert "API Gateway" in content


@pytest.mark.anyio
async def test_memory_server_stdio(ensure_db):
    test_user = "test-smoke-user"
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "graph_intelligence.memory.mcp_server"],
        env={
            **os.environ,
            "FALKORDB_GRAPH": ensure_db,
            "DEMO_USER_ID": test_user,
        },
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools_res = await session.list_tools()
            tool_names = [t.name for t in tools_res.tools]
            assert "remember_session_summary" in tool_names
            assert "search_user_memory" in tool_names
            assert "update_user_memory" in tool_names
            assert "get_user_memory_timeline" in tool_names
            assert "get_memory_status" in tool_names

            # 1. remember_session_summary
            write_res = await session.call_tool(
                "remember_session_summary",
                arguments={
                    "title": "Smoke Test Architecture Decision",
                    "summary": "We chose three Python MCP services over FalkorDB graph.",
                    "keywords": ["falkordb", "mcp", "smoke"],
                    "entities": ["PaymentService"],
                },
            )
            assert not write_res.isError
            assert "sum_" in write_res.content[0].text

            # 2. search_user_memory
            search_res = await session.call_tool(
                "search_user_memory",
                arguments={
                    "query": "What did we decide about FalkorDB MCP smoke architecture?",
                    "keywords": ["falkordb", "mcp"],
                },
            )
            assert not search_res.isError
            assert "Smoke Test Architecture Decision" in search_res.content[0].text

            # 3. get_memory_status
            status_res = await session.call_tool("get_memory_status", arguments={})
            assert not status_res.isError
            assert test_user in status_res.content[0].text

    # Cleanup smoke user summaries
    store = GraphStore(graph_name=ensure_db)
    store.query("MATCH (s:SessionSummary) WHERE s.user_id = $uid DETACH DELETE s", {"uid": test_user})


@pytest.mark.anyio
async def test_brain_server_stdio(ensure_db):
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "graph_intelligence.company_brain.mcp_server"],
        env={**os.environ, "FALKORDB_GRAPH": ensure_db},
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools_res = await session.list_tools()
            tool_names = [t.name for t in tools_res.tools]
            assert "search_company_knowledge" in tool_names
            assert "get_service_brief" in tool_names
            assert "get_decision_context" in tool_names
            assert "answer_company_question" in tool_names
            assert "ingest_company_records" in tool_names

            # Test answer_company_question
            q = "Who owns PaymentService, which team are they on, why did GraphCortex choose idempotency keys, and which document supports that decision?"
            call_res = await session.call_tool("answer_company_question", arguments={"question": q})
            assert not call_res.isError
            content = call_res.content[0].text
            assert "Maya Chen" in content
            assert "doc-adr-014" in content
