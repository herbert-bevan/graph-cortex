"""graphcortex-memory MCP server."""

from typing import Any, Dict, List, Optional
from mcp.server.fastmcp import FastMCP
from pydantic import Field
from graph_intelligence.common.identity import TrustedIdentity
from graph_intelligence.common.logging_setup import log_operation
from graph_intelligence.memory.service import MemoryService

SERVER_INSTRUCTIONS = """
PERSISTENT USER MEMORY POLICY

You have user-scoped memory tools via MCP. They persist information outside this
conversation. Use them deliberately. Never pretend to remember anything that was
not returned by a memory tool or stated in the current conversation.

WRITE
- When the user says remember this / save this / save a session summary / preserve
  this for later / record decisions or open tasks, call remember_session_summary.
  Do NOT just print a summary in chat.
- Include: goal, decisions and reasons, important entities, keywords, current state,
  open tasks, next steps. Never store passwords, tokens, secrets.
- Only confirm saving AFTER the tool returns ok=true; quote the returned summary_id.

READ
- If a new request mentions a project, entity, decision, feature, incident or topic
  that plausibly overlaps earlier saved work, call search_user_memory BEFORE answering.
  Pass the question plus meaningful keywords/entities.
- If the user says continue / resume / as discussed / what did we decide / next steps,
  ALWAYS search memory first instead of asking them to repeat context.
- Use only returned memory. State clearly when you are using remembered context
  (cite summary_id and saved date). If ambiguous, name the likely match and ask one
  short question. If nothing is found, say so and continue without it.

UPDATE
- If the user corrects, extends, or removes saved context, call update_user_memory.
  Never claim an update/removal happened unless the tool confirms it.
- Memory is private to the configured user. Never ask for or pass another user's identity.
"""

mcp = FastMCP("graphcortex-memory", instructions=SERVER_INSTRUCTIONS)


def _get_service() -> MemoryService:
    identity = TrustedIdentity.current()
    return MemoryService(user_id=identity.user_id)


@mcp.tool()
def remember_session_summary(
    title: str = Field(..., description="Concise title for the session summary (max 120 chars)"),
    summary: str = Field(..., description="Comprehensive markdown summary of session progress, architectural choices, and context (max 4000 chars)"),
    keywords: List[str] = Field(..., description="List of 3 to 15 key technical topics or domain tags for retrieval (e.g. ['falkordb', 'mcp', 'memory'])"),
    entities: List[str] = Field(default=[], description="List of specific services, features, decisions, or incidents mentioned (e.g. ['PaymentService', 'ADR-014'])"),
    project: Optional[str] = Field(None, description="Optional project name or ID associated with this session (e.g. 'proj-payment-reliability')"),
    decisions: List[str] = Field(default=[], description="List of concrete decisions reached during this session"),
    open_tasks: List[str] = Field(default=[], description="List of pending action items, next steps, or open tasks"),
    importance: str = Field("normal", description="Importance level: 'low', 'normal', or 'high'"),
    session_id: Optional[str] = Field(None, description="Optional client-specified session ID; auto-generated if omitted"),
) -> Dict[str, Any]:
    """
    Save a user-scoped session summary to persistent FalkorDB memory.
    Call this tool whenever the user asks to save, remember, record, or preserve session context or next steps for future conversations.
    """
    with log_operation("remember_session_summary"):
        service = _get_service()
        return service.remember_session_summary(
            title=title,
            summary=summary,
            keywords=keywords,
            entities=entities,
            project=project,
            decisions=decisions,
            open_tasks=open_tasks,
            importance=importance,
            session_id=session_id,
        )


@mcp.tool()
def search_user_memory(
    query: str = Field(..., description="Natural language search query or topic to search for in past session summaries"),
    keywords: List[str] = Field(default=[], description="Optional specific search keywords to boost scoring"),
    entities: List[str] = Field(default=[], description="Optional specific entity names to boost scoring (e.g. ['PaymentService'])"),
    project: Optional[str] = Field(None, description="Optional project filter"),
    limit: int = Field(5, description="Maximum number of memory summaries to return (1 to 10)"),
    include_superseded: bool = Field(False, description="Set True to include older superseded summary versions"),
) -> Dict[str, Any]:
    """
    Search previously stored session memories for the current user using deterministic graph and keyword scoring.
    ALWAYS call this tool at the start of a conversation when the user refers to past decisions, previous discussions, or resuming work.
    """
    with log_operation("search_user_memory"):
        service = _get_service()
        return service.search_user_memory(
            query=query,
            keywords=keywords,
            entities=entities,
            project=project,
            limit=limit,
            include_superseded=include_superseded,
        )


@mcp.tool()
def update_user_memory(
    summary_id: str = Field(..., description="ID of the SessionSummary to update (e.g. 'sum_abc123')"),
    update_type: str = Field(..., description="Type of update: 'append_context', 'correct', 'supersede', or 'archive'"),
    updated_summary: Optional[str] = Field(None, description="New summary content (for correct/supersede) or addendum text (for append_context)"),
    add_open_tasks: List[str] = Field(default=[], description="New open tasks to add"),
    complete_tasks: List[str] = Field(default=[], description="Existing tasks to mark as completed (matched by task description)"),
    reason: str = Field(..., description="Mandatory reason explaining the update or revision"),
    expected_version: Optional[int] = Field(None, description="Optional expected version of the summary being updated to prevent concurrent conflicts"),
) -> Dict[str, Any]:
    """
    Update, supersede, or archive a previously saved user session summary.
    Maintains an audit trail by linking superseded versions with SUPERSEDES relationships.
    """
    with log_operation("update_user_memory"):
        service = _get_service()
        return service.update_user_memory(
            summary_id=summary_id,
            update_type=update_type,
            updated_summary=updated_summary,
            add_open_tasks=add_open_tasks,
            complete_tasks=complete_tasks,
            reason=reason,
            expected_version=expected_version,
        )


@mcp.tool()
def get_user_memory_timeline(
    topic: Optional[str] = Field(None, description="Optional topic filter"),
    project: Optional[str] = Field(None, description="Optional project filter"),
    include_superseded: bool = Field(True, description="Whether to include superseded versions in the timeline"),
    limit: int = Field(20, description="Maximum number of historical timeline entries to return"),
) -> Dict[str, Any]:
    """
    Retrieve the historical timeline of session summaries for the active user, showing version progression and status.
    """
    with log_operation("get_user_memory_timeline"):
        service = _get_service()
        return service.get_user_memory_timeline(
            topic=topic,
            project=project,
            include_superseded=include_superseded,
            limit=limit,
        )


@mcp.tool()
def get_memory_status() -> Dict[str, Any]:
    """
    Retrieve persistent memory status counts (active, superseded, archived) for the currently configured user.
    Call this tool to verify memory persistence and health.
    """
    with log_operation("get_memory_status"):
        service = _get_service()
        return service.get_memory_status()


if __name__ == "__main__":
    mcp.run()
