"""Unified Remote MCP Server (SSE) & Guest Auth Portal.

Provides:
1. Web UI at `/` and `/login` for instant 1-click guest token generation.
2. FastMCP SSE endpoint at `/sse` and `/messages/` with Bearer auth.
3. Strict tenant isolation binding `user_id` to authenticated `guest_id`.
4. Sandboxed memory, company knowledge Q&A, and blast-radius reasoning.
5. Ingestion tool omitted to prevent database pollution by guests or attackers.
"""

import contextvars
from datetime import datetime, timezone
import json
import os
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from mcp.server.fastmcp import FastMCP
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
)

logger = get_logger("remote_server")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Automatic zero-touch database provisioning on server boot."""
    try:
        init_db()
        logger.info("GraphCortex PostgreSQL guest authentication tables verified.")
    except Exception as exc:
        logger.warning(f"PostgreSQL initialization note: {exc}")

    try:
        store = GraphStore()
        store.ensure_indexes()
        logger.info("GraphCortex FalkorDB schema indexes verified.")
    except Exception as exc:
        logger.warning(f"FalkorDB initialization note: {exc}")

    yield


# Context variable to hold the active authenticated guest ID for the current request
active_guest_context: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "active_guest_context", default=None
)

# ---------------------------------------------------------------------------
# FastMCP Server Setup
# ---------------------------------------------------------------------------
mcp = FastMCP(
    name="graph-cortex",
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
    return _get_memory_svc().get_user_memory_timeline(project=project, limit=min(limit, 20))


@mcp.tool(
    name="get_memory_status",
    description="Get counts of active, superseded, and archived memories for the current user.",
)
def get_memory_status() -> Dict[str, Any]:
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
    return _get_brain_svc().search_company_knowledge(query=query[:250], entity_types=entity_types, limit=limit)


@mcp.tool(
    name="get_service_brief",
    description="Retrieve the complete architectural profile of a service: owners, team, dependencies, features, and ADRs.",
)
def get_service_brief(service: str) -> Dict[str, Any]:
    return _get_brain_svc().get_service_brief(service=service)


@mcp.tool(
    name="get_decision_context",
    description="Retrieve the rationale, status, and affected services for an Architecture Decision Record (ADR).",
)
def get_decision_context(decision: str) -> Dict[str, Any]:
    return _get_brain_svc().get_decision_context(decision=decision)


@mcp.tool(
    name="answer_company_question",
    description="Ask a question about enterprise services, teams, ownership, ADRs, or incidents with source citations.",
)
def answer_company_question(
    question: str,
    project: Optional[str] = None,
) -> Dict[str, Any]:
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
    """Inspects SSE requests, enforces Bearer token validation and logs sessions."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Protect /sse and /messages routes
        if path.startswith("/sse") or path.startswith("/messages"):
            auth_header = request.headers.get("Authorization", "")
            raw_token = ""
            if auth_header.startswith("Bearer "):
                raw_token = auth_header[7:].strip()
            elif "token" in request.query_params:
                raw_token = request.query_params["token"].strip()

            if not raw_token:
                return JSONResponse(
                    {
                        "error": "unauthorized",
                        "message": "Missing Bearer token. Please visit / to generate a guest access token.",
                    },
                    status_code=401,
                )

            validation = validate_guest_token(raw_token)
            if not validation.get("valid"):
                reason = validation.get("reason", "invalid_token")
                msg = validation.get("message", f"Authentication failed: {reason}")
                status_code = 403 if reason == "quota_exceeded" else 401
                return JSONResponse({"error": reason, "message": msg}, status_code=status_code)

            guest_id = validation["guest_id"]
            # Bind contextvar for downstream tool execution
            token_reset = active_guest_context.set(guest_id)

            # Record session activity
            sess_id = request.headers.get("X-Session-ID") or request.query_params.get("session_id") or "sess_default"
            try:
                record_session_operation(guest_id, sess_id, path)
            except Exception as e:
                logger.warning(f"Failed to record session operation: {e}")

            try:
                response = await call_next(request)
                return response
            finally:
                active_guest_context.reset(token_reset)

        return await call_next(request)


app.add_middleware(GuestAuthMiddleware)


# ---------------------------------------------------------------------------
# Web Portal UI (HTML) & APIs
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
@app.get("/login", response_class=HTMLResponse)
@app.get("/portal", response_class=HTMLResponse)
async def portal_page(request: Request):
    """Serve the minimal guest auth portal."""
    base_url = str(request.base_url).rstrip("/")
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>GraphCortex | Live Agent Memory & Reasoning Demo</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg: #090d16;
      --card-bg: #111827;
      --card-border: #1f2937;
      --primary: #3b82f6;
      --primary-hover: #2563eb;
      --accent: #10b981;
      --text: #f9fafb;
      --text-muted: #9ca3af;
      --code-bg: #030712;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Plus Jakarta Sans', -apple-system, sans-serif;
      background: radial-gradient(circle at 50% 0%, #172554 0%, var(--bg) 75%);
      color: var(--text);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 1.5rem;
    }}
    .container {{
      max-width: 680px;
      width: 100%;
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 16px;
      padding: 2.5rem;
      box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: rgba(16, 185, 129, 0.1);
      color: var(--accent);
      border: 1px solid rgba(16, 185, 129, 0.2);
      font-size: 0.75rem;
      font-weight: 600;
      padding: 4px 10px;
      border-radius: 9999px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 1.25rem;
    }}
    h1 {{ font-size: 1.75rem; font-weight: 700; margin-bottom: 0.5rem; letter-spacing: -0.02em; }}
    p.subtitle {{ color: var(--text-muted); font-size: 0.95rem; line-height: 1.5; margin-bottom: 1.75rem; }}
    .form-group {{ margin-bottom: 1.25rem; }}
    label {{ display: block; font-size: 0.85rem; font-weight: 600; margin-bottom: 0.5rem; color: #e5e7eb; }}
    input[type="text"] {{
      width: 100%;
      padding: 0.75rem 1rem;
      background: var(--code-bg);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      color: var(--text);
      font-size: 0.95rem;
      outline: none;
      transition: border-color 0.15s ease;
    }}
    input[type="text"]:focus {{ border-color: var(--primary); }}
    button.btn-primary {{
      width: 100%;
      padding: 0.85rem 1.5rem;
      background: var(--primary);
      color: white;
      border: none;
      border-radius: 8px;
      font-size: 0.95rem;
      font-weight: 600;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      transition: background 0.15s ease;
    }}
    button.btn-primary:hover {{ background: var(--primary-hover); }}
    .result-box {{
      margin-top: 1.75rem;
      padding-top: 1.75rem;
      border-top: 1px solid var(--card-border);
      display: none;
    }}
    .code-container {{
      position: relative;
      background: var(--code-bg);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 1rem;
      margin-top: 0.75rem;
    }}
    pre {{
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.82rem;
      color: #93c5fd;
      overflow-x: auto;
      white-space: pre-wrap;
    }}
    .btn-copy {{
      position: absolute;
      top: 10px;
      right: 10px;
      background: rgba(255, 255, 255, 0.1);
      border: 1px solid rgba(255, 255, 255, 0.15);
      color: white;
      font-size: 0.75rem;
      padding: 4px 8px;
      border-radius: 4px;
      cursor: pointer;
    }}
    .btn-copy:hover {{ background: rgba(255, 255, 255, 0.2); }}
    .info-grid {{
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 0.75rem;
      margin-top: 1rem;
    }}
    .info-card {{
      background: rgba(255, 255, 255, 0.03);
      padding: 0.75rem;
      border-radius: 6px;
      border: 1px solid rgba(255, 255, 255, 0.05);
    }}
    .info-card .label {{ font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase; }}
    .info-card .val {{ font-size: 0.9rem; font-weight: 600; color: #60a5fa; margin-top: 2px; }}
    .footer {{ margin-top: 1.5rem; text-align: center; font-size: 0.8rem; color: var(--text-muted); }}
  </style>
</head>
<body>
  <div class="container">
    <div class="badge">● Live FalkorDB MCP Playground</div>
    <h1>GraphCortex</h1>
    <p class="subtitle">
      Connect your AI agent (Claude Desktop, Cursor, or Antigravity) directly to our live FalkorDB knowledge graph. Test cross-session autonomous memory, dependency blast radius, and grounded Q&A with zero vector embeddings.
    </p>

    <div class="form-group">
      <label for="nickname">Your Nickname (No email or personal data required)</label>
      <input type="text" id="nickname" placeholder="e.g. Alex" value="GuestDeveloper">
    </div>

    <button class="btn-primary" id="generateBtn" onclick="generateToken()">
      <span>Generate 1-Click Agent Access Token</span>
    </button>

    <div class="result-box" id="resultBox">
      <h3 style="font-size: 1rem; margin-bottom: 0.25rem;">Your Agent MCP Configuration</h3>
      <p style="font-size: 0.82rem; color: var(--text-muted);">
        Paste this into your <code>claude_desktop_config.json</code> or Antigravity MCP settings:
      </p>

      <div class="code-container">
        <button class="btn-copy" onclick="copyConfig()">Copy JSON</button>
        <pre><code id="configJson"></code></pre>
      </div>

      <div class="info-grid">
        <div class="info-card">
          <div class="label">Session Quota</div>
          <div class="val" id="quotaVal">10 Sessions</div>
        </div>
        <div class="info-card">
          <div class="label">Sandbox Retention</div>
          <div class="val" id="ttlVal">24 Hours (Auto-purged)</div>
        </div>
      </div>
    </div>
  </div>

  <div class="footer">
    Protected by FalkorDB Graph Sandboxing • Rate limited to 3 tokens/hour per IP
  </div>

  <script>
    async function generateToken() {{
      const btn = document.getElementById('generateBtn');
      const nickname = document.getElementById('nickname').value || 'GuestDeveloper';
      btn.innerText = 'Provisioning Sandbox...';
      btn.disabled = true;

      try {{
        const res = await fetch('/api/guest', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ nickname: nickname }})
        }});

        const data = await res.json();
        if (!res.ok) {{
          alert(data.message || 'Error creating guest token');
          btn.innerText = 'Generate 1-Click Agent Access Token';
          btn.disabled = false;
          return;
        }}

        const config = {{
          "mcpServers": {{
            "graph-cortex": {{
              "url": "{base_url}/sse",
              "headers": {{
                "Authorization": "Bearer " + data.token
              }}
            }}
          }}
        }};

        document.getElementById('configJson').innerText = JSON.stringify(config, null, 2);
        document.getElementById('quotaVal').innerText = data.session_quota + ' Sessions Left';
        document.getElementById('ttlVal').innerText = 'Valid for ' + data.ttl_hours + ' Hours';
        document.getElementById('resultBox').style.display = 'block';
        btn.innerText = 'Token Generated Successfully';
      }} catch (err) {{
        alert('Network error: ' + err);
        btn.innerText = 'Generate 1-Click Agent Access Token';
        btn.disabled = false;
      }}
    }}

    function copyConfig() {{
      const text = document.getElementById('configJson').innerText;
      navigator.clipboard.writeText(text);
      alert('Copied MCP configuration JSON to clipboard!');
    }}
  </script>
</body>
</html>
"""
    return HTMLResponse(content=html_content)


@app.post("/api/guest")
async def api_create_guest(request: Request):
    """Generate guest token with IP rate-limiting and global capacity checking."""
    # Extract client IP
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else "127.0.0.1"

    body = {}
    try:
        body = await request.json()
    except Exception:
        pass

    nickname = body.get("nickname") or "GuestDeveloper"
    success, result = create_guest(nickname=nickname, ip_address=client_ip)
    if not success:
        return JSONResponse(result, status_code=429 if result.get("error") == "rate_limit_exceeded" else 503)

    return JSONResponse(result)


@app.get("/api/quota")
async def api_check_quota(request: Request):
    """Check remaining session quota for the bearer token."""
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:].strip() if auth_header.startswith("Bearer ") else ""
    if not token:
        return JSONResponse({"error": "missing_token"}, status_code=401)

    validation = validate_guest_token(token)
    return JSONResponse(validation)


@app.post("/api/admin/cleanup")
async def api_trigger_cleanup(request: Request):
    """Scheduled task endpoint to purge expired guest accounts."""
    deleted_count = cleanup_expired_guests()
    return JSONResponse({"ok": True, "deleted_guests": deleted_count})


# Mount FastMCP SSE transport after all explicit Web & API routes
mcp_sse_app = mcp.sse_app()
app.mount("/", mcp_sse_app)

