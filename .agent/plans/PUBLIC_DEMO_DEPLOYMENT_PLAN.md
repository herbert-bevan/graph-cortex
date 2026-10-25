# Public Demo Deployment & Guest Access Architecture Plan

This document outlines the end-to-end plan to safely deploy the **FalkorDB Graph Intelligence Platform** as a publicly accessible remote Model Context Protocol (MCP) service on a VPS, complete with guest-tier authentication, PostgreSQL-backed session/quota management, and FalkorDB write hardening.

---

## 1. Feasibility Assessment & Domain vs. IP Recommendation

### 1.1 Is this feasible?
**Yes, 100% feasible and highly recommended for your LinkedIn launch.** 
Allowing readers to actually paste an MCP configuration into Claude Desktop, Cursor, or Antigravity and test cross-session memory live will make your LinkedIn post 10x more impactful than a static code dump.

### 1.2 Direct VPS IP vs. Domain (Critical Decision)

> [!CAUTION]
> **Do NOT use a bare VPS IP directly for a public MCP deployment.**

Here is why using a direct IP (`http://123.45.67.89:8000/sse`) will fail for end users:
1. **MCP Client Protocol Rejections**: Modern MCP clients (Claude Desktop, Cursor, VS Code, Antigravity) enforce standard transport rules. Connecting to an unencrypted HTTP endpoint over the public internet often triggers mixed-content security blocks, corporate firewall rejections, or transport failures.
2. **Let's Encrypt TLS Requires a Domain**: You cannot issue automated, trusted free Let's Encrypt certificates to a bare IP address. Without SSL/TLS (`https://`), any tokens sent in headers travel in plain text across the wire.
3. **Reputation & Security**: Exposing your raw VPS IP on LinkedIn invites automated botnets, port scanners, and DDoS attacks directly to your host.

### The Recommended Solution (Zero Extra Cost)
You **do NOT need to buy a new domain**. Use one of these three free options:
* **Option A (Best - Cloudflare Tunnel)**: 
  * If you already own any personal domain (e.g. `yourname.com`), install `cloudflared` on your VPS.
  * Route `https://mcp-demo.yourname.com` directly to your local container port via a free Cloudflare Tunnel.
  * **Benefits**: 100% Free SSL, automatic DDoS mitigation, zero open firewall ports on your VPS, and your VPS IP remains completely hidden.
* **Option B (Existing Domain Subdomain + Caddy/Nginx)**: 
  * Add a DNS `A` record: `demo.yourdomain.com -> YOUR_VPS_IP`.
  * Put **Caddy** in front of your container. Caddy automatically provisions and renews Let's Encrypt SSL with zero configuration.
* **Option C (Free Dynamic DNS like nip.io or duckdns)**:
  * If you have no domain, use a wildcard DNS provider like `<vps-ip>.nip.io` with Caddy for automatic SSL certificates.

---

## 2. High-Level Architecture Topology

```mermaid
flowchart TD
  subgraph Public_Internet["Public Internet"]
    User["LinkedIn Reader / User"]
    Client["AI Agent (Claude Desktop / Cursor / Antigravity)"]
  end

  subgraph Reverse_Proxy["Edge & Security Layer (VPS)"]
    CF["Cloudflare / Caddy Reverse Proxy<br/>(HTTPS Termination + Rate Limiting)"]
  end

  subgraph Application_Containers["Docker Compose Environment"]
    AuthWeb["Guest Auth Portal<br/>(FastAPI /login Webpage)"]
    MCPServer["FalkorDB Remote MCP Server<br/>(FastMCP SSE Transport)"]
    PG[(PostgreSQL<br/>Quota, Sessions & Guest Accounts)]
    Falkor[(FalkorDB<br/>Company Brain & Sandboxed Memory)]
  end

  User -->|1. Visit /login in Browser| CF
  CF --> AuthWeb
  AuthWeb -->|Create Guest Token & Quota| PG
  AuthWeb -->>|2. Returns Copy-Paste MCP Config JSON| User

  User -->|3. Pastes Config into| Client
  Client -->|4. JSON-RPC over HTTPS /sse<br/>Header: Authorization Bearer gst_xxx| CF
  CF --> MCPServer
  MCPServer -->|5. Validate Token, Check Quota & Log Session| PG
  MCPServer -->|6. Grounded Traversal & Sandboxed Memories| Falkor
```

---

## 3. End-to-End Guest Onboarding & Auth Flow

Because desktop MCP clients (like Claude Desktop or Antigravity) do not yet support interactive OAuth browser redirects inside their JSON-RPC connection handshakes, the smoothest UX is **One-Click Token Generation**:

### Step 1: User Visits Web Portal
* User visits `https://demo.yourdomain.com`.
* A clean, minimal page displays:
  * Field: "Nickname" (e.g., *Alex*). No email, password, or PII required.
  * Explanatory badge: *"Guest Access: 10 sessions, 24-hour retention"*.
  * Button: **"Generate Agent Access Token"**.

### Step 2: Server Provisions Guest in Postgres
The backend executes:
1. Generates an ephemeral guest ID (`gst_9f8a2b4c`) and an API key (`key_live_...`).
2. Inserts into PostgreSQL with:
   * `session_limit = 10`
   * `sessions_used = 0`
   * `expires_at = NOW() + INTERVAL '24 HOURS'`
   * `status = 'active'`

### Step 3: Portal Displays Instant Config Snippet
The web portal renders a one-click copy block:

```json
{
  "mcpServers": {
    "graph-cortex": {
      "url": "https://demo.yourdomain.com/sse",
      "headers": {
        "Authorization": "Bearer gst_9f8a2b4c1d2e3f"
      }
    }
  }
}
```

The user pastes this into their `claude_desktop_config.json` or Antigravity MCP settings.

---

## 4. PostgreSQL Schema Design (Guest & Session Engine)

PostgreSQL acts as the security and gatekeeping tier:

```sql
-- 1. Guest Users Table
CREATE TABLE guest_users (
    id VARCHAR(64) PRIMARY KEY,              -- e.g. 'gst_9f8a2b4c'
    nickname VARCHAR(64) NOT NULL,          -- e.g. 'Alex'
    api_token_hash VARCHAR(128) NOT NULL,   -- SHA-256 hash of the bearer token
    session_quota INT DEFAULT 10,           -- Maximum 10 sessions
    sessions_used INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,        -- 24 hours from creation
    is_revoked BOOLEAN DEFAULT FALSE
);

-- 2. Guest Session Audit Log
CREATE TABLE guest_session_logs (
    id VARCHAR(64) PRIMARY KEY,              -- 'sess_abc123'
    guest_id VARCHAR(64) REFERENCES guest_users(id) ON DELETE CASCADE,
    session_name VARCHAR(128),
    operation_count INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_active TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Optional: Guest Memory Fallback / Audit Records
CREATE TABLE guest_memory_backups (
    id VARCHAR(64) PRIMARY KEY,
    guest_id VARCHAR(64) REFERENCES guest_users(id) ON DELETE CASCADE,
    session_id VARCHAR(64),
    summary_title TEXT,
    summary_text TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for lightning-fast token validation and cleanup
CREATE INDEX idx_guest_users_token ON guest_users(api_token_hash);
CREATE INDEX idx_guest_users_expires ON guest_users(expires_at);
```

### Automated 24-Hour Cleanup Job (Postgres & FalkorDB)
A lightweight cron/worker runs every hour:
```sql
-- Delete expired guests (cascades to session logs and backups)
DELETE FROM guest_users WHERE expires_at < NOW();
```
And runs a Cypher statement against FalkorDB:
```cypher
MATCH (u:User)
WHERE u.is_guest = true AND u.expires_at < $now_iso
OPTIONAL MATCH (u)-[:OWNS_MEMORY]->(s:SessionSummary)
OPTIONAL MATCH (s)-[:HAS_TASK]->(t:Task)
DETACH DELETE u, s, t
```

---

## 5. Security & FalkorDB Write Hardening Plan

Publicly exposing any write tool risks database pollution, prompt injection, and DoS. Here is the multi-layered defense strategy:

### 5.1 Restrict Tool Surface Area for Guests
On the public remote server:
1. **Disable Ingestion**: Completely unregister or reject `ingest_company_records`.
2. **Make Company Brain Strictly Read-Only**: Ensure `search_company_knowledge`, `get_service_brief`, `get_decision_context`, and `answer_company_question` only execute read Cypher queries (`MATCH ... RETURN`).
3. **Scoped User Memory Writes Only**:
   * The only write tool allowed is `remember_session_summary` and `update_user_memory`.
   * The `user_id` is locked to the authenticated `guest_id` from the bearer token.
   * A guest cannot modify or delete company nodes (`Service`, `Team`, `Decision`). Cypher queries only create `(u:User {id: $guest_id})-[:OWNS_MEMORY]->(s:SessionSummary)`.

### 5.2 Quota & Abuse Protections in Middleware
* **Session Quota Enforcement**: If `sessions_used >= session_quota`, the MCP server responds with an error:
  `"Guest demo limit reached (10/10 sessions). Please reset or spin up the local open-source repo."`
* **Payload Length Limits**: Cap title to 100 characters, summary text to 1,500 characters, keywords to 5 items.
* **Secret & Malware Scanning**: Existing Shannon-entropy scanner in `validation.py` already drops credentials and toxic payload patterns.
* **Rate Limiting (Token Bucket)**: Maximum 30 tool calls per minute per guest IP/token.

---

## 6. Implementation Milestones & Checklist

```
Milestone 1: FastMCP Remote Transport (SSE)
├── [ ] Create remote MCP entrypoint (`src/graph_intelligence/remote/server.py`)
├── [ ] Mount FastMCP with SSE transport on Starlette/FastAPI
└── [ ] Add Bearer Token Auth middleware extracting `guest_id` from HTTP headers

Milestone 2: Postgres Guest Manager & Auth Portal
├── [ ] Create minimal FastAPI routes:
│   ├── GET /login -> Serves simple HTML form (Name input + Generate button)
│   ├── POST /api/guest -> Creates token in Postgres, returns JSON config
│   └── GET /api/quota -> Checks remaining sessions
└── [ ] Implement session increment logic on each MCP session handshake

Milestone 3: FalkorDB Tenant Sandboxing & Isolation
├── [ ] Verify all write queries enforce `(u:User {id: guest_id})`
├── [ ] Tag guest nodes with `is_guest: true` and `expires_at: timestamp`
└── [ ] Add scheduled cleanup job removing expired guest nodes from FalkorDB & Postgres

Milestone 4: Deployment & Edge Hardening
├── [ ] Update `docker-compose.yml` with:
│   ├── falkordb
│   ├── postgres
│   ├── mcp-server (app)
│   └── caddy (or cloudflared tunnel)
├── [ ] Configure SSL termination & domain routing
└── [ ] Test remote connection from Claude Desktop & Antigravity via SSE
```

---

## 7. Next Immediate Action

Once you confirm this plan:
1. We will create the remote SSE wrapper for FastMCP.
2. We will write the lightweight guest auth portal and Postgres connection adapter.
3. We will provide the exact `docker-compose.yml` and Caddy/Cloudflare configuration for your VPS.
