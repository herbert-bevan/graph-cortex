"""Unified Remote MCP Server (SSE) & Guest Auth Portal.

Provides:
1. Web UI at `/` and `/login` for instant 1-click guest token generation.
2. FastMCP SSE endpoint at `/sse` and `/messages/` with Bearer auth.
3. Strict tenant isolation binding `user_id` to authenticated `guest_id`.
4. Sandboxed memory, company knowledge Q&A, and blast-radius reasoning.
5. Ingestion tool omitted to prevent database pollution by guests or attackers.
"""

import asyncio
import contextvars
from datetime import datetime, timezone
import json
import os
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.base import BaseHTTPMiddleware

from contextlib import asynccontextmanager
from graph_intelligence.common.config import get_settings
from graph_intelligence.common.falkordb_client import GraphStore
from graph_intelligence.common.logging_setup import get_logger
from graph_intelligence.company_brain.service import CompanyBrainService
from graph_intelligence.memory.service import MemoryService
from graph_intelligence.reasoning.service import ReasoningService
from graph_intelligence.remote.auth import (
    create_guest,
    validate_guest_token,
    record_session_operation,
    cleanup_expired_guests,
    init_db,
    get_db_info,
    _USE_POSTGRES,
)
from graph_intelligence.remote.cleanup import cleanup_stale_records_and_graphs

logger = get_logger("remote_server")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Automatic zero-touch database provisioning on server boot with dynamic diagnostics."""
    db_info = get_db_info()
    try:
        init_db()
        logger.info(f"GraphCortex Auth Database ready: engine='{db_info['engine']}', target='{db_info['target']}'")
    except Exception as exc:
        logger.warning(f"Database initialization note ({db_info['target']}): {exc}")

    settings = get_settings()
    try:
        store = GraphStore()
        store.ensure_indexes()
        logger.info(
            f"GraphCortex FalkorDB indexes verified: host='{settings.FALKORDB_HOST}', port={settings.FALKORDB_PORT}, graph='{settings.FALKORDB_GRAPH}', ssl={settings.FALKORDB_SSL}"
        )
    except Exception as exc:
        logger.warning(f"FalkorDB initialization note ({settings.FALKORDB_HOST}:{settings.FALKORDB_PORT}/{settings.FALKORDB_GRAPH}): {exc}")

    # Automated daily cleanup background worker (runs once a day)
    async def _daily_cleanup_worker():
        await asyncio.sleep(120)  # Wait 2 minutes after startup before initial run
        while True:
            try:
                logger.info("Executing scheduled daily cleanup of dead records and graphs...")
                stats = cleanup_stale_records_and_graphs(days=2)
                logger.info(f"Scheduled daily cleanup finished: {stats}")
            except Exception as ex:
                logger.warning(f"Scheduled daily cleanup worker note: {ex}")
            await asyncio.sleep(86400)  # 24 hours

    cleanup_task = asyncio.create_task(_daily_cleanup_worker())
    try:
        yield
    finally:
        cleanup_task.cancel()


# Context variable to hold the active authenticated guest ID for the current request
active_guest_context: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "active_guest_context", default=None
)

# ---------------------------------------------------------------------------
# FastMCP Server Setup
# ---------------------------------------------------------------------------
mcp = FastMCP(
    name="graph-cortex",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    ),
    instructions="""
You are connected to the GraphCortex Platform.
You have access to 3 core capabilities:
1. Architectural Reasoning: Analyze service dependencies, blast radiuses, and shortest graph paths.
2. Autonomous Memory: Read, write, and search persistent user session summaries. Decisions and tasks are preserved deterministically across sessions.
3. Corporate Knowledge Brain: Grounded, fact-checked architectural questions regarding services, teams, owners, and Architecture Decision Records (ADRs).
""",
)

# Service factories
def _get_reasoning_svc() -> ReasoningService:
    return ReasoningService()

def _get_brain_svc() -> CompanyBrainService:
    return CompanyBrainService()

def _get_memory_svc() -> MemoryService:
    guest_id = active_guest_context.get()
    effective_user = guest_id or get_settings().DEMO_USER_ID
    return MemoryService(user_id=effective_user)


# ===========================================================================
# 1. Architectural Reasoning Tools
# ===========================================================================

@mcp.tool(
    name="find_service_dependencies",
    description="Traverse upstream dependencies or downstream dependents for a service in the architectural graph.",
)
def find_service_dependencies(
    service: str,
    direction: str = "both",
    max_depth: int = 2,
    limit: int = 25,
) -> Dict[str, Any]:
    caller = active_guest_context.get() or "demo_user"
    logger.info(f"[TOOL:find_service_dependencies] caller={caller}, service='{service}', direction='{direction}', max_depth={max_depth}")
    return _get_reasoning_svc().find_service_dependencies(
        service=service,
        direction=direction,
        max_depth=max_depth,
        limit=limit,
    )


@mcp.tool(
    name="analyze_change_impact",
    description="Calculate the blast radius of modifying a service, feature, or architectural decision.",
)
def analyze_change_impact(
    target: str,
    target_type: str = "Service",
    change_description: Optional[str] = None,
) -> Dict[str, Any]:
    caller = active_guest_context.get() or "demo_user"
    logger.info(f"[TOOL:analyze_change_impact] caller={caller}, target='{target}', target_type='{target_type}'")
    return _get_reasoning_svc().analyze_change_impact(
        target=target,
        target_type=target_type,
        change_description=change_description,
    )


@mcp.tool(
    name="find_graph_path",
    description="Find the shortest architectural relationship path connecting any two entities.",
)
def find_graph_path(
    source: str,
    target: str,
    max_hops: int = 4,
) -> Dict[str, Any]:
    caller = active_guest_context.get() or "demo_user"
    logger.info(f"[TOOL:find_graph_path] caller={caller}, source='{source}', target='{target}', max_hops={max_hops}")
    return _get_reasoning_svc().find_graph_path(
        source=source,
        target=target,
        max_hops=max_hops,
    )


@mcp.tool(
    name="search_connected_entities",
    description="Search for entities by keyword or alias and retrieve immediate 1-hop connections.",
)
def search_connected_entities(
    query: str,
    entity_types: Optional[List[str]] = None,
    limit: int = 10,
) -> Dict[str, Any]:
    caller = active_guest_context.get() or "demo_user"
    logger.info(f"[TOOL:search_connected_entities] caller={caller}, query='{query}'")
    return _get_reasoning_svc().search_connected_entities(
        query=query,
        entity_types=entity_types,
        limit=limit,
    )


# ===========================================================================
# 2. Autonomous Memory Engine Tools (Tenant Sandboxed)
# ===========================================================================

@mcp.tool(
    name="remember_session_summary",
    description="Persist an architectural decision, session summary, keywords, and action tasks for future recall.",
)
def remember_session_summary(
    title: str,
    summary: str,
    keywords: List[str] = [],
    entities: List[str] = [],
    project: Optional[str] = None,
    decisions: List[str] = [],
    open_tasks: List[str] = [],
    session_id: Optional[str] = None,
    importance: str = "normal",
) -> Dict[str, Any]:
    # Enforce strict length limits for guest tier protection
    title = title[:120]
    summary = summary[:2000]
    keywords = [k[:40] for k in keywords[:10]]
    decisions = [d[:200] for d in decisions[:8]]
    open_tasks = [t[:200] for t in open_tasks[:8]]

    caller = active_guest_context.get() or "demo_user"
    logger.info(f"[TOOL:remember_session_summary] caller={caller}, title='{title}', project='{project}', tasks={len(open_tasks)}, decisions={len(decisions)}")
    return _get_memory_svc().remember_session_summary(
        title=title,
        summary=summary,
        keywords=keywords,
        entities=entities,
        project=project,
        decisions=decisions,
        open_tasks=open_tasks,
        session_id=session_id,
        importance=importance,
    )


@mcp.tool(
    name="search_user_memory",
    description="Deterministically retrieve past session summaries, architectural decisions, and tasks by query topic.",
)
def search_user_memory(
    query: str,

    keywords: List[str] = [],
    entities: List[str] = [],
    project: Optional[str] = None,
    limit: int = 5,
    include_superseded: bool = False,
) -> Dict[str, Any]:
    caller = active_guest_context.get() or "demo_user"
    logger.info(f"[TOOL:search_user_memory] caller={caller}, query='{query}', project='{project}'")
    return _get_memory_svc().search_user_memory(
        query=query[:250],
        keywords=[k[:40] for k in keywords[:10]],
        entities=entities[:5],
        project=project,
        limit=min(limit, 10),
        include_superseded=include_superseded,
    )


@mcp.tool(
    name="update_user_memory",
    description="Evolve an existing memory summary by appending context, correcting decisions, or superseding history.",
)
def update_user_memory(
    summary_id: str,
    action: str,
    new_summary: Optional[str] = None,
    appended_context: Optional[str] = None,
    new_decisions: Optional[List[str]] = None,
    new_tasks: Optional[List[str]] = None,
    completed_task_ids: Optional[List[str]] = None,
    new_keywords: Optional[List[str]] = None,
    new_importance: Optional[str] = None,
    expected_version: Optional[int] = None,
) -> Dict[str, Any]:
    caller = active_guest_context.get() or "demo_user"
    logger.info(f"[TOOL:update_user_memory] caller={caller}, summary_id='{summary_id}', action='{action}'")
    return _get_memory_svc().update_user_memory(
        summary_id=summary_id,
        action=action,
        new_summary=new_summary[:2000] if new_summary else None,
        appended_context=appended_context[:1000] if appended_context else None,
        new_decisions=[d[:200] for d in (new_decisions or [])[:8]],
        new_tasks=[t[:200] for t in (new_tasks or [])[:8]],
        completed_task_ids=completed_task_ids,
        new_keywords=[k[:40] for k in (new_keywords or [])[:10]],
        new_importance=new_importance,
        expected_version=expected_version,
    )


@mcp.tool(
    name="get_user_memory_timeline",
    description="Fetch a chronological timeline of saved memories and version evolution.",
)
def get_user_memory_timeline(
    project: Optional[str] = None,
    limit: int = 15,
) -> Dict[str, Any]:
    caller = active_guest_context.get() or "demo_user"
    logger.info(f"[TOOL:get_user_memory_timeline] caller={caller}, project='{project}'")
    return _get_memory_svc().get_user_memory_timeline(project=project, limit=min(limit, 20))


@mcp.tool(
    name="get_memory_status",
    description="Get counts of active, superseded, and archived memories for the current user.",
)
def get_memory_status() -> Dict[str, Any]:
    caller = active_guest_context.get() or "demo_user"
    logger.info(f"[TOOL:get_memory_status] caller={caller}")
    return _get_memory_svc().get_memory_status()


# ===========================================================================
# 3. Corporate Knowledge Brain Tools (Read-Only)
# ===========================================================================

@mcp.tool(
    name="search_company_knowledge",
    description="Search company architecture entities and associated documentation catalogs.",
)
def search_company_knowledge(
    query: str,
    entity_types: Optional[List[str]] = None,
    limit: int = 10,
) -> Dict[str, Any]:
    caller = active_guest_context.get() or "demo_user"
    logger.info(f"[TOOL:search_company_knowledge] caller={caller}, query='{query}'")
    return _get_brain_svc().search_company_knowledge(query=query[:250], entity_types=entity_types, limit=limit)


@mcp.tool(
    name="get_service_brief",
    description="Retrieve the complete architectural profile of a service: owners, team, dependencies, features, and ADRs.",
)
def get_service_brief(service: str) -> Dict[str, Any]:
    caller = active_guest_context.get() or "demo_user"
    logger.info(f"[TOOL:get_service_brief] caller={caller}, service='{service}'")
    return _get_brain_svc().get_service_brief(service=service)


@mcp.tool(
    name="get_decision_context",
    description="Retrieve the rationale, status, and affected services for an Architecture Decision Record (ADR).",
)
def get_decision_context(decision: str) -> Dict[str, Any]:
    caller = active_guest_context.get() or "demo_user"
    logger.info(f"[TOOL:get_decision_context] caller={caller}, decision='{decision}'")
    return _get_brain_svc().get_decision_context(decision=decision)


@mcp.tool(
    name="answer_company_question",
    description="Ask a question about enterprise services, teams, ownership, ADRs, or incidents with source citations.",
)
def answer_company_question(
    question: str,
    project: Optional[str] = None,
) -> Dict[str, Any]:
    caller = active_guest_context.get() or "demo_user"
    logger.info(f"[TOOL:answer_company_question] caller={caller}, question='{question}', project='{project}'")
    return _get_brain_svc().answer_company_question(question=question[:300], project=project)


# ---------------------------------------------------------------------------
# FastAPI Web Portal & Middleware Setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="GraphCortex Demo Portal",
    description="GraphCortex Model Context Protocol (MCP) Remote Service with Guest Authentication & FalkorDB Knowledge Graph",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class GuestAuthMiddleware(BaseHTTPMiddleware):
    """Inspects SSE requests, enforces Bearer token validation, logs IP, user, and sessions."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Protect /sse and /messages routes
        if path.startswith("/sse") or path.startswith("/messages"):
            forwarded = request.headers.get("x-forwarded-for")
            client_ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")

            auth_header = request.headers.get("Authorization", "")
            raw_token = ""
            if auth_header.startswith("Bearer "):
                raw_token = auth_header[7:].strip()
            elif "token" in request.query_params:
                raw_token = request.query_params["token"].strip()

            if not raw_token:
                logger.warning(f"MCP unauthorized request: missing Bearer token, path={path}, ip={client_ip}")
                return JSONResponse(
                    {
                        "error": "unauthorized",
                        "message": "Missing Bearer token. Please visit / to generate a guest access token.",
                    },
                    status_code=401,
                )

            validation = validate_guest_token(raw_token, ip_address=client_ip)
            if not validation.get("valid"):
                reason = validation.get("reason", "invalid_token")
                msg = validation.get("message", f"Authentication failed: {reason}")
                logger.warning(f"MCP auth rejected: reason={reason}, path={path}, ip={client_ip}")
                status_code = 403 if reason == "quota_exceeded" else 401
                return JSONResponse({"error": reason, "message": msg}, status_code=status_code)

            guest_id = validation["guest_id"]
            user_name = validation.get("nickname", "unknown")
            token_reset = active_guest_context.set(guest_id)

            # Record session activity
            sess_id = request.headers.get("X-Session-ID") or request.query_params.get("session_id") or "sess_default"
            try:
                record_session_operation(guest_id, sess_id, path, ip_address=client_ip)
            except Exception as e:
                logger.warning(f"Failed to record session operation for guest={guest_id}: {e}")

            logger.info(
                f"MCP request authorized: guest_id='{guest_id}', user='{user_name}', path={path}, session_id='{sess_id}', ip={client_ip}, sessions_used={validation.get('sessions_used')}/{validation.get('session_quota')}"
            )

            try:
                response = await call_next(request)
                return response
            finally:
                active_guest_context.reset(token_reset)

        return await call_next(request)


app.add_middleware(GuestAuthMiddleware)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Web Portal UI (HTML) & APIs
# ---------------------------------------------------------------------------

PORTAL_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>GraphCortex | Autonomous Agent Memory & Graph Reasoning</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #070b14;
      --card-bg: rgba(15, 23, 42, 0.75);
      --card-border: rgba(51, 65, 85, 0.6);
      --card-hover: rgba(30, 41, 59, 0.85);
      --primary: #3b82f6;
      --primary-hover: #2563eb;
      --primary-glow: rgba(59, 130, 246, 0.25);
      --accent: #10b981;
      --accent-glow: rgba(16, 185, 129, 0.2);
      --purple: #8b5cf6;
      --purple-glow: rgba(139, 92, 246, 0.25);
      --amber: #f59e0b;
      --cyan: #06b6d4;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --code-bg: #030712;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
      background: radial-gradient(circle at 50% 0%, #1e1b4b 0%, #0f172a 35%, var(--bg) 85%);
      color: var(--text);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 2.5rem 1.25rem;
      line-height: 1.5;
    }
    .main-wrapper {
      max-width: 1060px;
      width: 100%;
      display: flex;
      flex-direction: column;
      gap: 2rem;
    }

    /* Header & Hero */
    .hero {
      text-align: center;
      padding: 1.5rem 0 0.5rem;
    }
    .badge-pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      background: rgba(16, 185, 129, 0.12);
      color: #34d399;
      border: 1px solid rgba(16, 185, 129, 0.3);
      font-size: 0.8rem;
      font-weight: 600;
      padding: 6px 14px;
      border-radius: 9999px;
      letter-spacing: 0.04em;
      margin-bottom: 1.25rem;
      backdrop-filter: blur(8px);
    }
    .status-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: #10b981;
      box-shadow: 0 0 10px #10b981;
      animation: pulse 2s infinite;
    }
    @keyframes pulse {
      0%, 100% { opacity: 1; transform: scale(1); }
      50% { opacity: 0.4; transform: scale(0.85); }
    }
    h1.hero-title {
      font-size: 2.6rem;
      font-weight: 800;
      letter-spacing: -0.03em;
      line-height: 1.15;
      background: linear-gradient(135deg, #ffffff 30%, #93c5fd 70%, #c084fc 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      margin-bottom: 0.85rem;
    }
    p.hero-desc {
      color: var(--text-muted);
      font-size: 1.1rem;
      max-width: 780px;
      margin: 0 auto 1.5rem;
      line-height: 1.6;
    }

    /* Core Card */
    .glass-card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 20px;
      padding: 2rem;
      backdrop-filter: blur(12px);
      box-shadow: 0 20px 40px -15px rgba(0, 0, 0, 0.6);
      transition: border-color 0.2s ease;
    }
    .glass-card:hover {
      border-color: rgba(99, 102, 241, 0.4);
    }

    /* Explainer Cards Grid */
    .grid-3 {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 1.25rem;
    }
    @media (max-width: 850px) {
      .grid-3 { grid-template-columns: 1fr; }
      h1.hero-title { font-size: 2rem; }
    }
    .feature-card {
      background: rgba(15, 23, 42, 0.5);
      border: 1px solid var(--card-border);
      border-radius: 14px;
      padding: 1.35rem;
      position: relative;
      overflow: hidden;
    }
    .feature-card::before {
      content: '';
      position: absolute;
      top: 0; left: 0; right: 0;
      height: 3px;
    }
    .card-guest::before { background: linear-gradient(90deg, #3b82f6, #60a5fa); }
    .card-quota::before { background: linear-gradient(90deg, #8b5cf6, #c084fc); }
    .card-privacy::before { background: linear-gradient(90deg, #10b981, #34d399); }
    .feature-icon {
      font-size: 1.6rem;
      margin-bottom: 0.75rem;
      display: inline-block;
    }
    .feature-title {
      font-size: 1.05rem;
      font-weight: 700;
      margin-bottom: 0.4rem;
      color: #ffffff;
    }
    .feature-text {
      font-size: 0.88rem;
      color: var(--text-muted);
      line-height: 1.5;
    }

    /* Auth Generator Section */
    .auth-section {
      background: linear-gradient(180deg, rgba(30, 41, 59, 0.4) 0%, rgba(15, 23, 42, 0.7) 100%);
      border: 1px solid rgba(99, 102, 241, 0.3);
      box-shadow: 0 0 35px -10px var(--primary-glow);
    }
    .input-row {
      display: flex;
      gap: 1rem;
      align-items: flex-end;
      margin-top: 1.25rem;
      flex-wrap: wrap;
    }
    .btn-dice {
      background: rgba(139, 92, 246, 0.15);
      border: 1px solid rgba(139, 92, 246, 0.35);
      color: #c084fc;
      font-size: 0.78rem;
      font-weight: 700;
      padding: 4px 10px;
      border-radius: 6px;
      cursor: pointer;
      transition: all 0.2s;
      display: inline-flex;
      align-items: center;
      gap: 5px;
    }
    .btn-dice:hover {
      background: rgba(139, 92, 246, 0.3);
      border-color: #c084fc;
      color: #fff;
      transform: translateY(-1px);
    }
    .input-group {
      flex: 1;
      min-width: 240px;
    }
    label.field-label {
      display: block;
      font-size: 0.85rem;
      font-weight: 600;
      margin-bottom: 0.5rem;
      color: #e2e8f0;
    }
    input[type="text"] {
      width: 100%;
      padding: 0.85rem 1.15rem;
      background: var(--code-bg);
      border: 1px solid var(--card-border);
      border-radius: 10px;
      color: var(--text);
      font-size: 0.95rem;
      font-family: inherit;
      outline: none;
      transition: all 0.2s;
    }
    input[type="text"]:focus {
      border-color: var(--primary);
      box-shadow: 0 0 12px var(--primary-glow);
    }
    button.btn-generate {
      padding: 0.85rem 1.75rem;
      background: linear-gradient(135deg, #2563eb, #3b82f6);
      color: white;
      border: none;
      border-radius: 10px;
      font-size: 0.95rem;
      font-weight: 700;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      transition: all 0.2s;
      white-space: nowrap;
      box-shadow: 0 4px 15px rgba(37, 99, 235, 0.35);
    }
    button.btn-generate:hover {
      background: linear-gradient(135deg, #1d4ed8, #2563eb);
      transform: translateY(-1px);
      box-shadow: 0 6px 20px rgba(37, 99, 235, 0.5);
    }
    button.btn-generate:disabled {
      opacity: 0.6;
      cursor: not-allowed;
      transform: none;
    }

    /* Result & Tabs */
    .result-section {
      margin-top: 1.75rem;
      padding-top: 1.75rem;
      border-top: 1px solid var(--card-border);
      display: none;
      animation: fadeIn 0.3s ease-in-out;
    }
    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(8px); }
      to { opacity: 1; transform: translateY(0); }
    }
    .metrics-row {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 1rem;
      margin-bottom: 1.5rem;
    }
    @media (max-width: 650px) {
      .metrics-row { grid-template-columns: 1fr; }
    }
    .metric-pill {
      background: rgba(3, 7, 18, 0.6);
      border: 1px solid var(--card-border);
      border-radius: 10px;
      padding: 0.85rem 1rem;
      display: flex;
      align-items: center;
      gap: 0.75rem;
    }
    .metric-pill .dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
    }
    .metric-pill .title { font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; font-weight: 600; }
    .metric-pill .value { font-size: 1rem; font-weight: 700; color: #fff; }

    /* Tabs */
    .tab-nav {
      display: flex;
      gap: 0.5rem;
      margin-bottom: 0.75rem;
      border-bottom: 1px solid var(--card-border);
      padding-bottom: 0.5rem;
    }
    .tab-btn {
      background: none;
      border: none;
      color: var(--text-muted);
      font-size: 0.85rem;
      font-weight: 600;
      padding: 0.45rem 0.9rem;
      border-radius: 6px;
      cursor: pointer;
      transition: all 0.15s;
    }
    .tab-btn:hover { color: #fff; background: rgba(255, 255, 255, 0.05); }
    .tab-btn.active {
      color: #60a5fa;
      background: rgba(59, 130, 246, 0.15);
      border: 1px solid rgba(59, 130, 246, 0.3);
    }
    .code-box {
      position: relative;
      background: var(--code-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 1.15rem;
    }
    pre code {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.84rem;
      color: #93c5fd;
      line-height: 1.6;
      overflow-x: auto;
      display: block;
      white-space: pre-wrap;
    }
    .btn-copy {
      position: absolute;
      top: 12px;
      right: 12px;
      background: rgba(255, 255, 255, 0.08);
      border: 1px solid rgba(255, 255, 255, 0.15);
      color: #e2e8f0;
      font-size: 0.75rem;
      font-weight: 600;
      padding: 6px 12px;
      border-radius: 6px;
      cursor: pointer;
      transition: all 0.15s;
      display: flex;
      align-items: center;
      gap: 5px;
    }
    .btn-copy:hover {
      background: rgba(255, 255, 255, 0.18);
      color: #fff;
    }

    /* Architecture Visual Diagram */
    .arch-diagram {
      margin-top: 1rem;
      background: #030712;
      border: 1px solid var(--card-border);
      border-radius: 16px;
      padding: 1.75rem;
      overflow-x: auto;
    }
    .diagram-title {
      font-size: 0.85rem;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 1.25rem;
      font-weight: 700;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .arch-flow {
      display: flex;
      align-items: stretch;
      justify-content: space-between;
      gap: 1rem;
      min-width: 820px;
    }
    .arch-column {
      flex: 1;
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
    }
    .arch-node {
      background: rgba(15, 23, 42, 0.9);
      border: 1px solid rgba(51, 65, 85, 0.8);
      border-radius: 10px;
      padding: 1rem;
      position: relative;
    }
    .node-header {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 0.88rem;
      font-weight: 700;
      color: #fff;
      margin-bottom: 4px;
    }
    .node-sub {
      font-size: 0.75rem;
      color: var(--text-muted);
      line-height: 1.35;
    }
    .arch-arrow {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      color: #475569;
      font-weight: 800;
      font-size: 1.2rem;
      padding: 0 0.25rem;
    }
    .arrow-label {
      font-size: 0.68rem;
      color: #64748b;
      margin-top: 4px;
      text-transform: uppercase;
      font-weight: 600;
      letter-spacing: 0.04em;
    }

    /* Prompt Cards */
    .prompts-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 1rem;
      margin-top: 1rem;
    }
    @media (max-width: 768px) {
      .prompts-grid { grid-template-columns: 1fr; }
    }
    .prompt-card {
      background: rgba(15, 23, 42, 0.5);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 1.1rem;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      transition: all 0.2s;
    }
    .prompt-card:hover {
      border-color: rgba(99, 102, 241, 0.5);
      background: rgba(30, 41, 59, 0.4);
    }
    .prompt-tag {
      font-size: 0.72rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 0.4rem;
    }
    .tag-memory { color: #34d399; }
    .tag-recall { color: #60a5fa; }
    .tag-impact { color: #f472b6; }
    .tag-graph { color: #fbbf24; }
    .prompt-title {
      font-size: 0.95rem;
      font-weight: 700;
      color: #fff;
      margin-bottom: 0.4rem;
    }
    .prompt-text {
      font-size: 0.82rem;
      color: var(--text-muted);
      margin-bottom: 0.85rem;
      font-style: italic;
    }
    .btn-copy-prompt {
      align-self: flex-start;
      background: rgba(255, 255, 255, 0.06);
      border: 1px solid rgba(255, 255, 255, 0.12);
      color: #cbd5e1;
      font-size: 0.75rem;
      font-weight: 600;
      padding: 4px 10px;
      border-radius: 6px;
      cursor: pointer;
      transition: all 0.15s;
    }
    .btn-copy-prompt:hover {
      background: rgba(255, 255, 255, 0.15);
      color: #fff;
    }

    /* Footer */
    .footer {
      text-align: center;
      font-size: 0.82rem;
      color: var(--text-muted);
      padding: 1.5rem 0 1rem;
      border-top: 1px solid rgba(51, 65, 85, 0.4);
    }
    .footer a {
      color: #60a5fa;
      text-decoration: none;
    }
    .footer a:hover { text-decoration: underline; }
  </style>
</head>
<body>
  <div class="main-wrapper">

    <!-- Hero Header -->
    <header class="hero">
      <div class="badge-pill">
        <span class="status-dot"></span>
        <span>GraphCortex MCP • Live FalkorDB Knowledge Graph</span>
      </div>
      <h1 class="hero-title">High-Performance Agent Memory & Reasoning</h1>
      <p class="hero-desc">
        A production Model Context Protocol (MCP) server powered by FalkorDB graph traversal and PostgreSQL guest sandboxes. Give Claude, Cursor, and custom AI agents real-time dependency reasoning, cross-session memory, and grounded architectural Q&A.
      </p>
    </header>

    <!-- 1-Click Guest Access Card -->
    <section class="glass-card auth-section">
      <h2 style="font-size: 1.35rem; font-weight: 700; margin-bottom: 0.35rem;">⚡ Instant 1-Click Guest Sandbox</h2>
      <p style="font-size: 0.9rem; color: var(--text-muted);">
        No signup, no emails, no credit cards. Enter any nickname to provision an isolated, tenant-sandboxed graph workspace for your agent in milliseconds.
      </p>

      <div class="input-row">
        <div class="input-group">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
            <label class="field-label" for="nickname" style="margin-bottom: 0;">Slayer Nickname</label>
            <button type="button" class="btn-dice" onclick="rollDemonSlayer()" title="Summon a random Demon Slayer character">
              🎲 Summon Demon Slayer
            </button>
          </div>
          <input type="text" id="nickname" placeholder="Zenitsu (Only Demon Slayer Character names are allowed)">
        </div>
        <button class="btn-generate" id="generateBtn" onclick="generateToken()">
          <span>⚡ Generate 1-Click Agent Token</span>
        </button>
      </div>

      <!-- Result View -->
      <div class="result-section" id="resultBox">
        <div class="metrics-row">
          <div class="metric-pill">
            <span class="dot" style="background: #34d399; box-shadow: 0 0 8px #34d399;"></span>
            <div>
              <div class="title">Active Token</div>
              <div class="value" id="guestNameVal" style="font-size: 0.95rem; color: #34d399;">Ready</div>
            </div>
          </div>
          <div class="metric-pill">
            <span class="dot" style="background: #60a5fa; box-shadow: 0 0 8px #60a5fa;"></span>
            <div>
              <div class="title">Session Quota</div>
              <div class="value" id="quotaVal">10 Sessions Available</div>
            </div>
          </div>
          <div class="metric-pill">
            <span class="dot" style="background: #c084fc; box-shadow: 0 0 8px #c084fc;"></span>
            <div>
              <div class="title">Sandbox Retention</div>
              <div class="value" id="ttlVal">24 Hours (Auto-Purged)</div>
            </div>
          </div>
        </div>

        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
          <h3 style="font-size: 1.05rem; font-weight: 700;">Client Configuration</h3>
          <span style="font-size: 0.78rem; color: var(--text-muted);">Select your AI environment:</span>
        </div>

        <div class="tab-nav">
          <button class="tab-btn active" id="tabClaudeBtn" onclick="switchTab('claude')">Claude Desktop</button>
          <button class="tab-btn" id="tabCursorBtn" onclick="switchTab('cursor')">Cursor IDE</button>
          <button class="tab-btn" id="tabAntigravityBtn" onclick="switchTab('antigravity')">Antigravity / Generic MCP</button>
        </div>

        <div class="code-box">
          <button class="btn-copy" onclick="copyConfig()">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
            <span id="copyBtnText">Copy Config</span>
          </button>
          <pre><code id="configJson"></code></pre>
        </div>
      </div>
    </section>

    <!-- Explainer 3-Card Grid: Guest Mode, Sessions, Quotas -->
    <section class="grid-3">
      <div class="feature-card card-guest">
        <span class="feature-icon">🛡️</span>
        <h3 class="feature-title">What is Guest Mode?</h3>
        <p class="feature-text">
          Zero-signup playground designed for instant agent testing. A cryptographic Bearer token creates a private tenant partition (<code>guest_&lt;id&gt;</code>) in FalkorDB. Your sessions, memories, and decisions are completely isolated and never visible to other users.
        </p>
      </div>

      <div class="feature-card card-quota">
        <span class="feature-icon">⏳</span>
        <h3 class="feature-title">Sessions & Quotas</h3>
        <p class="feature-text">
          Each guest receives a quota of <strong>10 active agent conversation sessions</strong> with a <strong>24-hour retention window</strong>. Plenty of capacity to test memory persistence across restarts, blast radius impact analysis, and knowledge graph queries.
        </p>
      </div>

      <div class="feature-card card-privacy">
        <span class="feature-icon">⚡</span>
        <h3 class="feature-title">How to Connect</h3>
        <p class="feature-text">
          Paste the generated config into Claude Desktop (<code>claude_desktop_config.json</code>) or Cursor settings. Our host Nginx streams tool calls via SSE (Server-Sent Events) with zero buffering and low millisecond response times.
        </p>
      </div>
    </section>

    <!-- Visual Architecture Diagram -->
    <section class="glass-card">
      <h2 style="font-size: 1.35rem; font-weight: 700; margin-bottom: 0.35rem;">🏗️ GraphCortex System Architecture</h2>
      <p style="font-size: 0.9rem; color: var(--text-muted); margin-bottom: 1.25rem;">
        How real-time AI agents interact with GraphCortex tri-core services over secure HTTPS SSE transport.
      </p>

      <div class="arch-diagram">
        <div class="diagram-title">
          <span>End-to-End Execution Flow</span>
          <span style="color: #10b981;">HTTPS / WSS / SSE Active</span>
        </div>
        <div class="arch-flow">
          
          <!-- Column 1: AI Clients -->
          <div class="arch-column">
            <div style="font-size: 0.75rem; font-weight: 700; color: #60a5fa; text-transform: uppercase;">1. AI Client Apps</div>
            <div class="arch-node" style="border-left: 3px solid #3b82f6;">
              <div class="node-header">🤖 Claude Desktop</div>
              <div class="node-sub">Native MCP SSE client</div>
            </div>
            <div class="arch-node" style="border-left: 3px solid #8b5cf6;">
              <div class="node-header">⚡ Cursor IDE</div>
              <div class="node-sub">Developer tool agent</div>
            </div>
            <div class="arch-node" style="border-left: 3px solid #ec4899;">
              <div class="node-header">🌌 Antigravity Agent</div>
              <div class="node-sub">Autonomous coding subagents</div>
            </div>
          </div>

          <!-- Arrow -->
          <div class="arch-arrow">
            <span>➔</span>
            <span class="arrow-label">Bearer Auth</span>
          </div>

          <!-- Column 2: Gateway & Auth -->
          <div class="arch-column" style="flex: 1.1;">
            <div style="font-size: 0.75rem; font-weight: 700; color: #a78bfa; text-transform: uppercase;">2. Gateway & Security</div>
            <div class="arch-node" style="border-left: 3px solid #a855f7;">
              <div class="node-header">🛡️ Host Nginx Reverse Proxy</div>
              <div class="node-sub">TLS/SSL Termination<br><code>proxy_buffering off;</code><br>Long-lived SSE Keep-Alive</div>
            </div>
            <div class="arch-node" style="border-left: 3px solid #6366f1;">
              <div class="node-header">🔑 Guest Auth Middleware</div>
              <div class="node-sub">Bearer Token Validation<br>IP Rate Limiting (3/hr)<br>Tenant Context Binding</div>
            </div>
          </div>

          <!-- Arrow -->
          <div class="arch-arrow">
            <span>➔</span>
            <span class="arrow-label">FastMCP SSE</span>
          </div>

          <!-- Column 3: GraphCortex Tri-Core -->
          <div class="arch-column" style="flex: 1.3;">
            <div style="font-size: 0.75rem; font-weight: 700; color: #34d399; text-transform: uppercase;">3. GraphCortex Engine</div>
            <div class="arch-node" style="border-left: 3px solid #10b981;">
              <div class="node-header">🧠 Memory Engine</div>
              <div class="node-sub">Cross-session summaries, keyword extraction, and chronological timelines.</div>
            </div>
            <div class="arch-node" style="border-left: 3px solid #06b6d4;">
              <div class="node-header">⚡ Reasoning Engine</div>
              <div class="node-sub">Transitive dependency tree, blast radius impact analysis, path finding.</div>
            </div>
            <div class="arch-node" style="border-left: 3px solid #f59e0b;">
              <div class="node-header">🏢 Enterprise Brain</div>
              <div class="node-sub">Grounded Q&amp;A on services, teams, ADRs, and incidents without vector drift.</div>
            </div>
          </div>

          <!-- Arrow -->
          <div class="arch-arrow">
            <span>➔</span>
            <span class="arrow-label">Cypher / SQL</span>
          </div>

          <!-- Column 4: Storage Engines -->
          <div class="arch-column">
            <div style="font-size: 0.75rem; font-weight: 700; color: #f43f5e; text-transform: uppercase;">4. Datastores</div>
            <div class="arch-node" style="border-left: 3px solid #ef4444;">
              <div class="node-header">🚀 FalkorDB Graph</div>
              <div class="node-sub">In-Memory Redis Cypher<br>Sandboxed Graph Nodes<br>&lt;15ms Graph Traversal</div>
            </div>
            <div class="arch-node" style="border-left: 3px solid #3b82f6;">
              <div class="node-header">🐘 PostgreSQL Ledger</div>
              <div class="node-sub">Guest Accounts &amp; Hashes<br>Session Usage Counting<br>Automatic 24h Purge</div>
            </div>
          </div>

        </div>
      </div>
    </section>

    <!-- Test Drive / Interactive Stories -->
    <section class="glass-card">
      <h2 style="font-size: 1.35rem; font-weight: 700; margin-bottom: 0.35rem;">🚀 Test-Drive Scenarios</h2>
      <p style="font-size: 0.9rem; color: var(--text-muted); margin-bottom: 1.25rem;">
        Copy and paste these prompts directly into your AI assistant to verify cross-session memory and graph reasoning in action:
      </p>

      <div class="prompts-grid">
        <div class="prompt-card">
          <div>
            <div class="prompt-tag tag-memory">Scenario 1 • Chat 1 (Write Memory)</div>
            <div class="prompt-title">Store Architectural Decision</div>
            <div class="prompt-text">
              "We decided to migrate payments to gRPC with idempotency keys. Persist this session decision into GraphCortex user memory."
            </div>
          </div>
          <button class="btn-copy-prompt" onclick="copyPrompt(this, 'We decided to migrate payments to gRPC with idempotency keys. Persist this session decision into GraphCortex user memory.')">Copy Prompt</button>
        </div>

        <div class="prompt-card">
          <div>
            <div class="prompt-tag tag-recall">Scenario 2 • Chat 2 (New Session Recall)</div>
            <div class="prompt-title">Cross-Chat Autonomous Recall</div>
            <div class="prompt-text">
              "Start a brand new chat: What did we decide about our payment migration in our previous session? Query user memory."
            </div>
          </div>
          <button class="btn-copy-prompt" onclick="copyPrompt(this, 'What did we decide about our payment migration in our previous session? Query user memory.')">Copy Prompt</button>
        </div>

        <div class="prompt-card">
          <div>
            <div class="prompt-tag tag-impact">Scenario 3 • Graph Reasoning</div>
            <div class="prompt-title">Blast Radius Impact Analysis</div>
            <div class="prompt-text">
              "What is the blast radius if we modify the Order Processing service? Analyze transitive dependency impacts."
            </div>
          </div>
          <button class="btn-copy-prompt" onclick="copyPrompt(this, 'What is the blast radius if we modify the Order Processing service? Analyze transitive dependency impacts.')">Copy Prompt</button>
        </div>

        <div class="prompt-card">
          <div>
            <div class="prompt-tag tag-graph">Scenario 4 • Grounded Q&amp;A</div>
            <div class="prompt-title">Enterprise Architecture Query</div>
            <div class="prompt-text">
              "Find the shortest dependency path connecting Payment Service and Notification Service in our architecture."
            </div>
          </div>
          <button class="btn-copy-prompt" onclick="copyPrompt(this, 'Find the shortest dependency path connecting Payment Service and Notification Service in our architecture.')">Copy Prompt</button>
        </div>
      </div>
    </section>

    <!-- Footer -->
    <footer class="footer">
      GraphCortex Engine • FalkorDB In-Memory Graph &amp; PostgreSQL Tenant Sandbox • Rate limited to 3 tokens/hour per IP
    </footer>

  </div>

  <script>
    let currentToken = '';
    let currentTab = 'claude';
    const baseUrl = '{{base_url}}';

    const demonSlayers = [
      "Zenitsu Agatsuma ⚡",
      "Tanjiro Kamado 🌊",
      "Nezuko Kamado 🎋",
      "Inosuke Hashibira 🐗",
      "Kyojuro Rengoku 🔥",
      "Giyu Tomioka 🌊",
      "Shinobu Kocho 🦋",
      "Tengen Uzui ✨",
      "Muichiro Tokito 🌫️",
      "Mitsuri Kanroji 💖",
      "Sanemi Shinazugawa 🌪️",
      "Gyomei Himejima 🪨",
      "Obanai Iguro 🐍",
      "Kanao Tsuyuri 🪙",
      "Genya Shinazugawa 💥",
      "Yoriichi Tsugikuni ☀️",
      "Muzan Kibutsuji 🎩",
      "Akaza ❄️",
      "Kokushibo 👁️",
      "Doma 🪭"
    ];

    function rollDemonSlayer() {
      const input = document.getElementById('nickname');
      const randomIndex = Math.floor(Math.random() * demonSlayers.length);
      input.value = demonSlayers[randomIndex];
      input.style.borderColor = '#c084fc';
      input.focus();
      setTimeout(() => { input.style.borderColor = ''; }, 600);
    }

    function getConfigs(token) {
      const sseUrl = baseUrl + '/sse';
      return {
        claude: {
          "mcpServers": {
            "graph-cortex": {
              "url": sseUrl,
              "headers": {
                "Authorization": "Bearer " + token
              }
            }
          }
        },
        cursor: {
          "mcpServers": {
            "graph-cortex": {
              "url": sseUrl,
              "headers": {
                "Authorization": "Bearer " + token
              }
            }
          }
        },
        antigravity: {
          "server": "graph-cortex",
          "transport": "sse",
          "url": sseUrl,
          "headers": {
            "Authorization": "Bearer " + token
          }
        }
      };
    }

    function renderConfig() {
      if (!currentToken) return;
      const configs = getConfigs(currentToken);
      document.getElementById('configJson').innerText = JSON.stringify(configs[currentTab], null, 2);
    }

    function switchTab(tab) {
      currentTab = tab;
      document.getElementById('tabClaudeBtn').classList.toggle('active', tab === 'claude');
      document.getElementById('tabCursorBtn').classList.toggle('active', tab === 'cursor');
      document.getElementById('tabAntigravityBtn').classList.toggle('active', tab === 'antigravity');
      renderConfig();
    }

    async function generateToken() {
      const btn = document.getElementById('generateBtn');
      const nickname = document.getElementById('nickname').value.trim() || 'Zenitsu Agatsuma ⚡';
      btn.innerHTML = '<span>⚡ Provisioning Sandbox...</span>';
      btn.disabled = true;

      try {
        const res = await fetch('/api/guest', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ nickname: nickname })
        });

        const data = await res.json();
        if (!res.ok) {
          alert(data.message || 'Error creating guest token');
          btn.innerHTML = '<span>⚡ Generate 1-Click Agent Token</span>';
          btn.disabled = false;
          return;
        }

        currentToken = data.token;
        document.getElementById('guestNameVal').innerText = (data.nickname || nickname) + ' (Active)';
        document.getElementById('quotaVal').innerText = data.session_quota + ' Sessions Available';
        document.getElementById('ttlVal').innerText = data.ttl_hours + ' Hours (Auto-Purged)';
        
        renderConfig();
        document.getElementById('resultBox').style.display = 'block';
        btn.innerHTML = '<span>✓ Token Provisioned</span>';
        
        // Smooth scroll to results
        document.getElementById('resultBox').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      } catch (err) {
        alert('Network error: ' + err);
        btn.innerHTML = '<span>⚡ Generate 1-Click Agent Token</span>';
        btn.disabled = false;
      }
    }

    function copyConfig() {
      const text = document.getElementById('configJson').innerText;
      navigator.clipboard.writeText(text);
      const btnText = document.getElementById('copyBtnText');
      btnText.innerText = 'Copied!';
      setTimeout(() => { btnText.innerText = 'Copy Config'; }, 2000);
    }

    function copyPrompt(btn, text) {
      navigator.clipboard.writeText(text);
      const original = btn.innerText;
      btn.innerText = 'Copied!';
      btn.style.color = '#34d399';
      setTimeout(() => {
        btn.innerText = original;
        btn.style.color = '';
      }, 2000);
    }
  </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
@app.get("/login", response_class=HTMLResponse)
@app.get("/portal", response_class=HTMLResponse)
async def portal_page(request: Request):
    """Serve the interactive guest auth and architecture portal."""
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("host", request.url.netloc)
    if "localhost" not in host and "127.0.0.1" not in host:
        proto = "https"
    base_url = f"{proto}://{host}".rstrip("/")
    html_content = PORTAL_HTML_TEMPLATE.replace("{{base_url}}", base_url)
    return HTMLResponse(content=html_content)


@app.post("/api/guest")
async def api_create_guest(request: Request):
    """Generate guest token with IP rate-limiting and global capacity checking."""
    forwarded = request.headers.get("X-Forwarded-For")
    client_ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "127.0.0.1")

    body = {}
    try:
        body = await request.json()
    except Exception:
        pass

    nickname = body.get("nickname") or "GuestDeveloper"
    logger.info(f"API /api/guest request received: nickname='{nickname}', ip={client_ip}")
    success, result = create_guest(nickname=nickname, ip_address=client_ip)
    if not success:
        logger.warning(f"API /api/guest request rejected: nickname='{nickname}', ip={client_ip}, error={result.get('error')}")
        return JSONResponse(result, status_code=429 if result.get("error") == "rate_limit_exceeded" else 503)

    logger.info(f"API /api/guest token issued: guest_id='{result.get('guest_id')}', user='{nickname}', ip={client_ip}")
    return JSONResponse(result)


@app.get("/api/quota")
async def api_check_quota(request: Request):
    """Check remaining session quota for the bearer token."""
    forwarded = request.headers.get("X-Forwarded-For")
    client_ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "127.0.0.1")

    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:].strip() if auth_header.startswith("Bearer ") else ""
    if not token:
        logger.warning(f"API /api/quota rejected: missing token, ip={client_ip}")
        return JSONResponse({"error": "missing_token"}, status_code=401)

    validation = validate_guest_token(token, ip_address=client_ip)
    logger.info(
        f"API /api/quota checked: guest_id='{validation.get('guest_id')}', user='{validation.get('nickname')}', valid={validation.get('valid')}, quota_left={validation.get('sessions_left')}, ip={client_ip}"
    )
    return JSONResponse(validation)


@app.get("/api/status")
async def api_status(request: Request):
    """Live runtime diagnostics: database engine, target, guest counts, and FalkorDB status."""
    from graph_intelligence.remote.auth import get_db_info, _get_connection
    db_info = get_db_info()

    guest_count = None
    db_error = None
    try:
        conn = _get_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM guest_users")
        guest_count = cur.fetchone()[0]
        conn.close()
    except Exception as e:
        db_error = str(e)

    falkordb_status = "unknown"
    node_count = None
    falkordb_error = None
    settings = get_settings()
    try:
        store = GraphStore()
        if store.ping():
            falkordb_status = "connected"
            res = store.query("MATCH (n) RETURN COUNT(n) AS count")
            if res and "count" in res[0]:
                node_count = res[0]["count"]
        else:
            falkordb_status = "ping_failed"
    except Exception as e:
        falkordb_status = "error"
        falkordb_error = str(e)

    return JSONResponse({
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": {
            "engine": db_info["engine"],
            "target": db_info["target"],
            "use_postgres": db_info["use_postgres"],
            "guest_count": guest_count,
            "error": db_error,
        },
        "falkordb": {
            "status": falkordb_status,
            "host": settings.FALKORDB_HOST,
            "port": settings.FALKORDB_PORT,
            "graph": settings.FALKORDB_GRAPH,
            "ssl": settings.FALKORDB_SSL,
            "node_count": node_count,
            "error": falkordb_error,
        },
    })


@app.post("/api/admin/cleanup")
async def api_trigger_cleanup(request: Request, days: int = 2):
    """Scheduled task endpoint to purge dead guest accounts, logs, and FalkorDB graph data older than `days` days."""
    stats = cleanup_stale_records_and_graphs(days=days)
    return JSONResponse({"ok": True, **stats})


# Mount FastMCP SSE transport after all explicit Web & API routes
mcp_sse_app = mcp.sse_app()
app.mount("/", mcp_sse_app)

