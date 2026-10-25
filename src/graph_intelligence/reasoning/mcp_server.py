"""graphcortex-reasoning MCP server."""

from typing import Any, Dict, List, Optional
from mcp.server.fastmcp import FastMCP
from pydantic import Field
from graph_intelligence.common.logging_setup import log_operation
from graph_intelligence.reasoning.service import ReasoningService

SERVER_INSTRUCTIONS = """
GraphCortex Reasoning Server.
Provides structural graph queries for service dependencies, blast-radius change impact analysis,
and shortest connection paths across microservices, features, decisions, and incidents.
Use this server when exploring system architecture, evaluating the impact of code or configuration changes,
or tracing relationships between services.
"""

mcp = FastMCP("graphcortex-reasoning", instructions=SERVER_INSTRUCTIONS)
_service = ReasoningService()


@mcp.tool()
def find_service_dependencies(
    service: str = Field(..., description="Service identifier, name, or alias (e.g. 'PaymentService', 'svc-payment', 'gateway')"),
    direction: str = Field("both", description="Direction of dependency traversal: 'dependencies' (services it needs), 'dependents' (services that need it), or 'both'"),
    max_depth: int = Field(2, description="Maximum traversal depth (1 to 4)"),
    limit: int = Field(25, description="Maximum number of connections to return (1 to 25)"),
) -> Dict[str, Any]:
    """
    Find upstream dependencies or downstream dependents of a service in the architectural graph.
    Call this tool when analyzing which services a microservice depends on, or which services rely on it.
    """
    with log_operation("find_service_dependencies"):
        return _service.find_service_dependencies(
            service=service,
            direction=direction,
            max_depth=max_depth,
            limit=limit,
        )


@mcp.tool()
def analyze_change_impact(
    target: str = Field(..., description="Target service, feature, or decision identifier or name (e.g. 'PaymentService', 'ADR-014')"),
    target_type: str = Field("Service", description="Type of target entity: 'Service', 'Feature', or 'Decision'"),
    change_description: Optional[str] = Field(None, description="Optional brief description of the proposed change (e.g. 'update retry policy with jitter')"),
) -> Dict[str, Any]:
    """
    Analyze the cascading blast radius and change impact of modifying a service, feature, or architecture decision.
    Returns authoritative graph-backed facts: affected dependents, underlying dependencies, implemented features,
    governing decisions, related historical incidents, service owners, and documentation references.
    Call this tool whenever an engineer or user asks about the consequences or risks of modifying system components.
    """
    with log_operation("analyze_change_impact"):
        return _service.analyze_change_impact(
            target=target,
            target_type=target_type,
            change_description=change_description,
        )


@mcp.tool()
def find_graph_path(
    source: str = Field(..., description="Starting entity identifier, name, or alias (e.g. 'API Gateway')"),
    target: str = Field(..., description="Destination entity identifier, name, or alias (e.g. 'LedgerService')"),
    max_hops: int = Field(4, description="Maximum number of relationship hops (1 to 6)"),
) -> Dict[str, Any]:
    """
    Find the shortest connection path between any two entities in the architectural graph.
    Call this tool when you need to understand how two components are connected across the architecture.
    """
    with log_operation("find_graph_path"):
        return _service.find_graph_path(
            source=source,
            target=target,
            max_hops=max_hops,
        )


@mcp.tool()
def search_connected_entities(
    query: str = Field(..., description="Search keyword, entity name, or alias to look up"),
    entity_types: Optional[List[str]] = Field(None, description="Optional list of entity labels to filter by (e.g. ['Service', 'Feature'])"),
    limit: int = Field(10, description="Maximum number of entities to return (1 to 10)"),
) -> Dict[str, Any]:
    """
    Search for graph entities matching keywords or names and inspect their immediate relationships.
    Call this tool to discover entity IDs or explore immediate neighbors of a concept.
    """
    with log_operation("search_connected_entities"):
        return _service.search_connected_entities(
            query=query,
            entity_types=entity_types,
            limit=limit,
        )


if __name__ == "__main__":
    mcp.run()
