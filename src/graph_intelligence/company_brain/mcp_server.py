"""graphcortex-brain MCP server."""

from typing import Any, Dict, List, Optional
from mcp.server.fastmcp import FastMCP
from pydantic import Field
from graph_intelligence.common.logging_setup import log_operation
from graph_intelligence.company_brain.service import CompanyBrainService

SERVER_INSTRUCTIONS = """
GraphCortex Knowledge Brain Server.
Provides source-backed, hallucination-free answers and authoritative architecture information
over the enterprise knowledge graph.
Use this server to look up service ownership, tech lead assignments, team structures,
architecture decision records (ADRs), incident reviews, runbooks, and design rationales.
Private user session memory is completely isolated and cannot be accessed from this server.
"""

mcp = FastMCP("graphcortex-brain", instructions=SERVER_INSTRUCTIONS)
_service = CompanyBrainService()


@mcp.tool()
def search_company_knowledge(
    query: str = Field(..., description="Entity name, technical term, or search topic (e.g. 'PaymentService', 'idempotency')"),
    entity_types: Optional[List[str]] = Field(None, description="Optional entity labels to filter by (e.g. ['Service', 'Decision'])"),
    limit: int = Field(10, description="Maximum number of results to return (1 to 20)"),
) -> Dict[str, Any]:
    """
    Search company knowledge base entities and their associated source documentation.
    Returns matched nodes alongside supporting documents and runbooks.
    """
    with log_operation("search_company_knowledge"):
        return _service.search_company_knowledge(
            query=query,
            entity_types=entity_types,
            limit=limit,
        )


@mcp.tool()
def get_service_brief(
    service: str = Field(..., description="Service identifier, name, or alias (e.g. 'PaymentService', 'svc-payment', 'gateway')"),
) -> Dict[str, Any]:
    """
    Retrieve an authoritative, comprehensive brief for an enterprise microservice.
    Includes technical ownership (lead + team), parent project, dependencies, downstream dependents,
    implemented features, past incidents, governing decisions, and source documents.
    """
    with log_operation("get_service_brief"):
        return _service.get_service_brief(service=service)


@mcp.tool()
def get_decision_context(
    decision: str = Field(..., description="Decision identifier, title, or alias (e.g. 'adr-014', 'idempotency keys')"),
) -> Dict[str, Any]:
    """
    Retrieve the full architectural context for an Architecture Decision Record (ADR).
    Includes the decision rationale, status, decided date, affected services,
    supporting documentation excerpts/URIs, and historical incidents that motivated the decision.
    """
    with log_operation("get_decision_context"):
        return _service.get_decision_context(decision=decision)


@mcp.tool()
def answer_company_question(
    question: str = Field(..., description="Natural language question about company architecture, ownership, or decisions"),
    project: Optional[str] = Field(None, description="Optional project context filter"),
) -> Dict[str, Any]:
    """
    Produce a deterministic, source-backed answer to an architectural or operational question.
    Extracts graph facts and cites exact source document IDs and URIs.
    Explicitly reports knowledge gaps if facts are missing from the graph.
    """
    with log_operation("answer_company_question"):
        return _service.answer_company_question(question=question, project=project)


@mcp.tool()
def ingest_company_records(
    source: Dict[str, str] = Field(..., description="Source metadata containing 'id' and 'title' (e.g. {'id': 'jira-sync-1', 'title': 'Jira Sync'})"),
    records: List[Dict[str, Any]] = Field(..., description="List of validated company node records with 'type', 'id', 'name', and optional 'properties'"),
    relationships: List[Dict[str, str]] = Field(default=[], description="List of validated relationships with 'type', 'from_id', 'to_id'"),
) -> Dict[str, Any]:
    """
    Ingest validated, structured company entities and relationships into the knowledge graph.
    Enforces strict label and relationship type allowlists. Cannot write to private user memory.
    """
    with log_operation("ingest_company_records"):
        return _service.ingest_company_records(
            source=source,
            records=records,
            relationships=relationships,
        )


if __name__ == "__main__":
    mcp.run()
