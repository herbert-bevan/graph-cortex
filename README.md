# GraphCortex: Autonomous Knowledge Graph Memory & Reasoning Engine for AI Agents

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Live Demo](https://img.shields.io/badge/Live%20Demo-graph--cortex.herbert.co.in-blue.svg)](https://graph-cortex.herbert.co.in)
[![FalkorDB](https://img.shields.io/badge/FalkorDB-Cloud-orange.svg)](https://www.falkordb.com/)
[![MCP](https://img.shields.io/badge/MCP-1.30-purple.svg)](https://modelcontextprotocol.io/)
[![Tests](https://img.shields.io/badge/tests-37%20tests-brightgreen.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An enterprise-grade Python platform delivering **three specialized Model Context Protocol (MCP) servers** over a single **FalkorDB knowledge graph** and a unified, secure domain core.

> [!TIP]
> **Live Demo & Interactive Playground**: Connect your agent immediately without local setup at **[https://graph-cortex.herbert.co.in](https://graph-cortex.herbert.co.in)**. Generate a 1-click sandboxed guest token and test architectural reasoning and autonomous memory directly in Google Antigravity, Claude Desktop, or Cursor!

Built specifically for advanced agentic AI environments (such as **Google Antigravity**, Claude Desktop, and VS Code), this platform bridges the gap between static codebases, corporate knowledge bases, and long-term agent memory without relying on vector embeddings or opaque embeddings-based semantic search.

---

## Table of Contents

1. [Executive Summary & Problem Statement](#1-executive-summary--problem-statement)
2. [System Architecture](#2-system-architecture)
3. [Graph Data Model & Schema](#3-graph-data-model--schema)
   - [Dual-Domain Architecture](#dual-domain-architecture)
   - [Entity-Relationship Diagram](#entity-relationship-diagram)
   - [Node Labels & Property Specifications](#node-labels--property-specifications)
   - [Relationship Taxonomy & Semantics](#relationship-taxonomy--semantics)
   - [Indexing & Schema Integrity in FalkorDB](#indexing--schema-integrity-in-falkordb)
4. [Deep Dive: The Three MCP Servers](#4-deep-dive-the-three-mcp-servers)
   - [Architectural Reasoning Engine: graphcortex-reasoning](#architectural-reasoning-engine-graphcortex-reasoning)
   - [Autonomous Memory Engine: graphcortex-memory](#autonomous-memory-engine-graphcortex-memory)
   - [Corporate Knowledge Brain: graphcortex-brain](#corporate-knowledge-brain-graphcortex-brain)
5. [Shared Domain Core & Security Boundaries](#5-shared-domain-core--security-boundaries)
6. [FalkorDB Field Learnings & Opportunities for Improvement](#6-falkordb-field-learnings--opportunities-for-improvement)
7. [Verification & Test Suite (33/33 Passing)](#7-verification--test-suite-3333-passing)
8. [Live Demo Runbook & Prompt Storyboard](#8-live-demo-runbook--prompt-storyboard)
9. [Setup Instructions & Deployment Guide](#9-setup-instructions--deployment-guide)
   - [Option A: 100% Local Setup (Docker + Local FalkorDB)](#option-a-100-local-setup-docker--local-falkordb)
   - [Option B: Cloud Setup (FalkorDB Cloud)](#option-b-cloud-setup-falkordb-cloud)
   - [Option C: Fully Containerized App](#option-c-fully-containerized-app)
   - [Testing Locally with MCP Inspector (`@modelcontextprotocol/inspector`)](#testing-locally-with-mcp-inspector-modelcontextprotocolinspector)
   - [Configuring MCP Clients (Antigravity, Claude Desktop, Cursor)](#configuring-mcp-clients)
   - [Local Troubleshooting & Diagnostic Guide](#local-troubleshooting--diagnostic-guide)
10. [Deep Architecture & File-by-File Code Flow](#10-deep-architecture--file-by-file-code-flow)

---

## 1. Executive Summary & Problem Statement

Large Language Models (LLMs) running inside agentic coding environments suffer from three critical deficiencies:
1. **Context Amnesia Across Conversations**: When a developer opens a new conversation or task, all prior decisions, agreed architectures, open tasks, and historical context are lost unless pasted manually.
2. **Hallucinated Blast Radius Analysis**: When asked about the downstream consequences of modifying an API or changing a retry policy, LLMs generate plausible-sounding guesses rather than tracing authoritative architectural dependencies.
3. **Unverifiable Corporate Knowledge Retrieval**: Traditional Retrieval-Augmented Generation (RAG) using vector search chunks documents arbitrarily, losing structural relationships between teams, services, Architecture Decision Records (ADRs), and incident postmortems.

### The Solution: FalkorDB Graph Intelligence Platform
This platform replaces unstructured vector search with **structured graph reasoning and deterministic scoring**:
- **Zero Vector DBs / Zero Embeddings**: Fast, deterministic keyword, token, entity squash matching, and graph-hop expansion.
- **The Definition of Done**: The user tells the LLM to remember an architectural decision in **Session A** → The LLM calls MCP `remember_session_summary` → FalkorDB persists the user-scoped record → In a **brand-new conversation (Session B)** with an empty context window, the user asks about the topic → The LLM autonomously calls `search_user_memory` → The summary is retrieved with scoring breakdown → The LLM answers accurately.
- **Strict Security & Scoping**: No raw Cypher execution tools (`no run_cypher`), no `user_id` leakage in tool schemas, backend-enforced tenant isolation, and payload secret scanning.

---

## 2. System Architecture

```mermaid
flowchart TD
  subgraph Agentic_Client["Agentic Client (e.g. Antigravity IDE)"]
    U[Developer / User] --> Agent[AI Coding Assistant]
    Rule[Memory Policy Rule: .agent/rules/memory-policy.md] -.-> Agent
  end

  subgraph MCP_Layer["Model Context Protocol (stdio transport)"]
    Agent -->|JSON-RPC stdio| M1["graphcortex-reasoning<br/>(4 Tools)"]
    Agent -->|JSON-RPC stdio| M2["graphcortex-memory<br/>(5 Tools)"]
    Agent -->|JSON-RPC stdio| M3["graphcortex-brain<br/>(5 Tools)"]
  end

  subgraph Core_Layer["Shared Python Domain Core (src/graph_intelligence/common/)"]
    M1 --> Core[Domain Core]
    M2 --> Core
    M3 --> Core
    Core --> Ident[identity.py: TrustedIdentity]
    Core --> Valid[validation.py: Secret Scanner & Bounds]
    Core --> Schema[schema.py: Allowlist Validator]
    Core --> Text[text.py: Normalization & Stemming]
    Core --> Adapter[falkordb_client.py: GraphStore Adapter]
  end

  subgraph Database_Layer["Graph Storage"]
    Adapter -->|Redis Protocol :63251| F[(FalkorDB Cloud<br/>Standalone Graph)]
    Seed[Idempotent Seeder: demo_data.json] --> F
  end
```

### Component Breakdown
1. **stdio Transport Layer**: MCP servers communicate over standard input/output using JSON-RPC 2.0. To prevent protocol corruption, **zero logging is emitted to stdout**; all telemetry, audit trails, and debug messages stream to `stderr` as structured JSON.
2. **Domain Core**: Business logic, query builders, validation, and parameter sanitization live strictly within Python domain classes. MCP tool handlers are ultra-thin wrappers that delegate to domain services.
3. **FalkorDB Client Adapter (`falkordb_client.py`)**: The single isolated gateway importing `falkordb`. Wraps driver exceptions into standard domain errors (`DatabaseUnavailable`), parses result headers into clean Python dictionaries, ensures schema indexes, and handles transient socket retries.

> [!TIP]
> For an exhaustive, file-by-file code flow, component breakdown, and execution traces of all 4 request lifecycles, see **[ARCHITECTURE_CODE_FLOW.md](ARCHITECTURE_CODE_FLOW.md)**.

---

## 3. Graph Data Model & Schema

The platform implements a unified property graph in FalkorDB with strict domain boundaries and schema validation.

### Dual-Domain Architecture

The graph cleanly segregates data into two isolated logical domains:
1. **Company Knowledge Domain (Global & Read-Only)**: Authoritative organizational architecture, service topology, ADRs, incidents, features, teams, and documents. Seeded during onboarding or structured ingestion; immutable during standard chat operations.
2. **User Memory Domain (Tenant-Isolated & Versioned)**: User-specific sessions, summaries, and tasks. Strictly scoped by `user_id` enforced server-side. Implements append-only versioning via `[:SUPERSEDES]` relationships.

### Entity-Relationship Diagram

```mermaid
erDiagram
  Company ||--o{ Team : "BELONGS_TO"
  Person ||--o{ Team : "MEMBER_OF"
  Person ||--o{ Service : "OWNS"
  Service ||--o{ Project : "PART_OF"
  Service ||--o{ Service : "DEPENDS_ON"
  Service ||--o{ Feature : "IMPLEMENTS"
  Incident ||--o{ Service : "AFFECTS"
  Decision ||--o{ Service : "AFFECTS"
  Decision ||--o{ Project : "MADE_FOR"
  Decision ||--o{ Document : "SUPPORTED_BY"
  Decision ||--o{ Incident : "RESPONDS_TO"
  Document ||--o{ Service : "DESCRIBES"
  Document ||--o{ Feature : "DESCRIBES"
  Document ||--o{ Incident : "DESCRIBES"
  Document ||--o{ Decision : "DESCRIBES"

  User ||--o{ SessionSummary : "OWNS_MEMORY"
  SessionSummary ||--o{ Session : "FROM_SESSION"
  SessionSummary ||--o{ Project : "ABOUT_PROJECT"
  SessionSummary ||--o{ Service : "MENTIONS_ENTITY"
  SessionSummary ||--o{ Incident : "MENTIONS_ENTITY"
  SessionSummary ||--o{ Decision : "MENTIONS_ENTITY"
  SessionSummary ||--o{ Feature : "MENTIONS_ENTITY"
  SessionSummary ||--o{ Document : "MENTIONS_ENTITY"
  SessionSummary ||--o{ Person : "MENTIONS_ENTITY"
  SessionSummary ||--o{ Team : "MENTIONS_ENTITY"
  SessionSummary ||--o{ SessionSummary : "SUPERSEDES"
  SessionSummary ||--o{ Task : "HAS_TASK"
```

### Node Labels & Property Specifications

All nodes in the graph share baseline metadata properties:
- `id` (String, Indexed): Unique identifier (e.g., `svc-payment`, `dec-adr-014`, `sum_295209b8f3c8`).
- `name` / `title` (String): Human-readable name or summary title.
- `created_at` (ISO 8601 String): Timestamp of initial creation.
- `updated_at` (ISO 8601 String): Timestamp of last modification.
- `source` (String): Origin provenance (`"seed"`, `"structured_ingestion"`, or `"llm_mcp_write"`).
- `source_ref` (Optional String): External reference link or document pointer.

#### 1. Company Knowledge Nodes
| Label | Key Properties | Description & Example |
|---|---|---|
| `Company` | `name`, `domain`, `founded` | Top-level enterprise root (e.g., *GraphCortex*). |
| `Team` | `name`, `mission`, `slack_channel` | Engineering or product teams (e.g., *Payments*, *Core Banking*). |
| `Person` | `name`, `role`, `email`, `timezone` | Engineers, architects, and owners (e.g., *Maya Chen, Staff Engineer*). |
| `Project` | `name`, `status`, `priority`, `description` | High-level initiatives (e.g., *Payment Reliability*, *status="in_progress"*). |
| `Service` | `name`, `tier`, `language`, `repo`, `description` | Microservices (e.g., *PaymentService, tier=1, language="Go"*). |
| `Feature` | `name`, `status`, `description` | System capabilities (e.g., *Idempotent Payment Processing*, *Bounded Retry Policy*). |
| `Incident` | `name`, `severity`, `status`, `postmortem_url` | Postmortems & outages (e.g., *INC-PAY-019, severity="sev1"*). |
| `Decision` | `name`, `status`, `rationale`, `accepted_date` | Architecture Decision Records (e.g., *ADR-014 Idempotency Keys*). |
| `Document` | `name`, `doc_type`, `uri`, `excerpt`, `content` | Documentation and runbooks (e.g., *doc-adr-014, type="adr"*). |

#### 2. User Memory Nodes
| Label | Key Properties | Description & Isolation Rule |
|---|---|---|
| `User` | `id`, `name`, `email`, `role` | Identity node anchoring private memory. |
| `Session` | `id`, `user_id`, `started_at`, `client` | Represents an interactive developer conversation turn. |
| `SessionSummary` | `id`, `user_id`, `session_id`, `title`, `summary`, `keywords`, `entity_keys`, `decisions`, `open_tasks_text`, `project_id`, `status`, `summary_version`, `content_hash` | Core memory record. `status` is `'active'`, `'superseded'`, or `'archived'`. Scoped strictly to `user_id`. |
| `Task` | `id`, `user_id`, `text`, `status`, `created_at` | Trackable action items extracted from session decisions (`'open'`, `'done'`). |

### Relationship Taxonomy & Semantics

| Edge Type | Source Label | Target Label | Semantic Meaning & Traversal Pattern |
|---|---|---|---|
| `BELONGS_TO` | `Team` | `Company` | Organizational hierarchy. |
| `MEMBER_OF` | `Person` | `Team` | Team staffing and escalation paths. |
| `OWNS` | `Person` | `Service` | Service ownership and code review routing. |
| `PART_OF` | `Service` | `Project` | Project service portfolio mapping. |
| `DEPENDS_ON` | `Service` | `Service` | Direct directional service call/RPC dependency (`A -> B`). Multi-hop traversals trace upstream load and downstream blast radius. |
| `IMPLEMENTS` | `Service` | `Feature` | Feature implementation mapping. |
| `AFFECTS` | `Incident` | `Service` | Historical incident attribution for reliability analysis. |
| `AFFECTS` | `Decision` | `Service` | Service architectural constraint tracking. |
| `MADE_FOR` | `Decision` | `Project` | Project-level architecture alignment. |
| `SUPPORTED_BY` | `Decision` | `Document` | Citation link connecting ADR to its canonical documentation. |
| `RESPONDS_TO` | `Decision` | `Incident` | Root-cause remediation tracking (ADRs triggered by postmortems). |
| `DESCRIBES` | `Document` | `Service`/`Feature`/`Incident`/`Decision` | Documentation linkage for source citations. |
| `OWNS_MEMORY` | `User` | `SessionSummary` | Security boundary mapping a user to their private memory nodes. |
| `FROM_SESSION` | `SessionSummary` | `Session` | Provenance link back to the originating chat session. |
| `ABOUT_PROJECT` | `SessionSummary` | `Project` | Project-scoped memory filtering. |
| `MENTIONS_ENTITY`| `SessionSummary` | `Service`/`Incident`/`Decision`/`Feature`/`Person`/`Team` | Entity linkage enabling graph-adjacency memory scoring (+2.0 per hop). |
| `SUPERSEDES` | `SessionSummary` | `SessionSummary` | Version lineage DAG (`v(n) -> v(n-1)`) for rollback and timeline history. |
| `HAS_TASK` | `SessionSummary` | `Task` | Action item ownership and carryover tracking across updates. |

### Indexing & Schema Integrity in FalkorDB

To achieve sub-millisecond query latency across thousands of nodes and traversals, `GraphStore.ensure_indexes()` guarantees the following indexes on FalkorDB:
- `CREATE INDEX FOR (n:Company) ON (n.id)`
- `CREATE INDEX FOR (n:Team) ON (n.id)`
- `CREATE INDEX FOR (n:Person) ON (n.id)`
- `CREATE INDEX FOR (n:Project) ON (n.id)`
- `CREATE INDEX FOR (n:Service) ON (n.id)`
- `CREATE INDEX FOR (n:Feature) ON (n.id)`
- `CREATE INDEX FOR (n:Incident) ON (n.id)`
- `CREATE INDEX FOR (n:Decision) ON (n.id)`
- `CREATE INDEX FOR (n:Document) ON (n.id)`
- `CREATE INDEX FOR (n:User) ON (n.id)`
- `CREATE INDEX FOR (n:Session) ON (n.id)`
- `CREATE INDEX FOR (n:SessionSummary) ON (n.id)`
- `CREATE INDEX FOR (n:SessionSummary) ON (n.user_id)`
- `CREATE INDEX FOR (n:Task) ON (n.id)`

---

## 4. Deep Dive: The Three MCP Servers

### Architectural Reasoning Engine: `graphcortex-reasoning`
Focuses on blast radius calculation, transitive dependencies, and graph connectivity.

#### Tools
1. **`find_service_dependencies(service, direction="both", max_depth=2, limit=25)`**:
   - `direction="dependencies"`: outgoing `[:DEPENDS_ON*1..depth]` (services this service needs).
   - `direction="dependents"`: incoming `[:DEPENDS_ON*1..depth]` (services that rely on this service).
   - `direction="both"`: bidirectional inspection with depth and path evidence.
2. **`analyze_change_impact(target, target_type="Service", change_description=None)`**:
   - Computes full architectural blast radius:
     - `dependents` (depth ≤3) — *"would be affected by interface/behavior change"*
     - `dependencies` (depth ≤2) — *"would see changed traffic/load"*
     - `features` (`[:IMPLEMENTS]`), `decisions` (`[:AFFECTS]`), `incidents` (`[:AFFECTS]`), `owners` (`[:OWNS]`), and `documents` (`[:DESCRIBES]`).
   - If target is a `Feature` or `Decision`, resolves the implementing/affected services and recurses.
3. **`find_graph_path(source, target, max_hops=4)`**:
   - Computes the shortest path between any two arbitrary nodes in the company graph using bounded Breadth-First Search (BFS) in Python over 1-hop neighbor queries.
4. **`search_connected_entities(query, entity_types=None, limit=10)`**:
   - Discovers entities matching squashed tokens or aliases and returns immediate 1-hop connections.

---

### Autonomous Memory Engine: `graphcortex-memory`
Implements user-scoped persistent session memory written and retrieved by the LLM.

#### Data Model (`SessionSummary`)
```python
{
    "id": "sum_a8f3b29c10de",
    "user_id": "demo-user-dev",
    "session_id": "ses_49e17b8c2d5a",
    "title": "Three MCP Services Architecture with FalkorDB",
    "summary": "We decided to use three Python MCP services over a shared FalkorDB graph...",
    "keywords": ["falkordb", "mcp", "memory", "architecture"],
    "entity_keys": ["PaymentService"],
    "decisions": ["Use three separate MCP servers"],
    "open_tasks_text": ["Implement shared core package", "Implement retrieval ranking"],
    "project_id": "proj-payment-reliability",
    "importance": "normal",
    "status": "active",  # 'active' | 'superseded' | 'archived'
    "summary_version": 1,
    "supersedes_id": None,
    "content_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "created_at": "2026-10-18T22:00:00+00:00",
}
```

#### Deterministic Retrieval Scoring Formula
When `search_user_memory` is invoked, candidates for the trusted `user_id` are scored deterministically in Python:

$$\text{Total Score} = S_{\text{entity}} + S_{\text{project}} + S_{\text{kw\_phrase}} + S_{\text{kw\_token}} + S_{\text{content}} + S_{\text{graph\_hop}} + S_{\text{recency}} - P_{\text{superseded}}$$

| Signal | Logic | Weight | Cap |
|---|---|---|---|
| **$S_{\text{entity}}$ (Entity Match)** | Resolved entity in query matches summary's linked entity or `entity_keys` | **+5.0** each | Max 15.0 |
| **$S_{\text{project}}$ (Project Match)** | Query project equals summary's `project_id` or `project_name` | **+4.0** | Max 4.0 |
| **$S_{\text{kw\_phrase}}$ (Keyword Phrase)** | Provided search keyword phrase matches a stored keyword | **+3.0** each | Max 12.0 |
| **$S_{\text{kw\_token}}$ (Keyword Tokens)** | Query/keyword token overlap with stored keyword tokens | **+2.0** each | Max 12.0 |
| **$S_{\text{content}}$ (Content Tokens)** | Token overlap with `title` or `summary` body | **+0.5** each | Max 3.0 |
| **$S_{\text{graph\_hop}}$ (Graph Adjacency)**| Summary links an entity directly adjacent (1 hop) to a query entity | **+2.0** | Max 4.0 |
| **$S_{\text{recency}}$ (Linear Decay)** | Linear decay over 30 days: $0.5 \times (1 - \frac{\text{days}}{30})$ | **0.0 to +0.5** | Max 0.5 |
| **$P_{\text{superseded}}$ (Penalty)** | Summary has `status == 'superseded'` | **-3.0** | - |

> **Threshold**: Summaries scoring below **3.0** are dropped. Results are sorted descending by score.

#### Lifecycle & Tools
- **`remember_session_summary(...)`**:
  - Computes SHA-256 hash of normalized title + summary. If identical active summary exists, returns with `deduplicated: true`.
  - Links resolved `Project` (`[:ABOUT_PROJECT]`) and `Service/Incident/Decision` (`[:MENTIONS_ENTITY]`).
  - Creates individual `Task` nodes (`[:HAS_TASK]`).
  - **Read-Back Verification**: Queries the database by ID and user ID before returning `ok: true`.
- **`update_user_memory(summary_id, update_type, ...)`**:
  - `archive`: Sets `status = 'archived'`.
  - `append_context`, `correct`, `supersede`: Creates new `SessionSummary` (`version = old + 1`), sets old summary status to `'superseded'`, creates `(new)-[:SUPERSEDES]->(old)` edge, marks completed tasks as `'done'`, and copies forward active tasks.
  - Enforces `expected_version` concurrency check (returns `CONFLICT` on mismatch).
- **`get_user_memory_timeline(...)`**: Returns chronological chain of memory records.
- **`get_memory_status()`**: Returns scoped memory counts (`active`, `superseded`, `archived`) for the configured user.

---

### Corporate Knowledge Brain: `graphcortex-brain`
Deterministic company knowledge search and Q&A over the synthetic **GraphCortex** fintech architecture.

#### Tools
- **`answer_company_question(question, project=None)`**:
  - **100% Deterministic & Hallucination-Free**: Does NOT invoke another LLM.
  - Resolves entities using a 60-second cached squash resolver.
  - Matches intent keywords (`owner`, `team`, `why/rationale`, `document`, `incident`, `dependency`, `feature`).
  - Runs allowlisted Cypher traversal templates.
  - Returns structured `facts` with graph `evidence_path` and cited `sources` (`id`, `title`, `uri`, `excerpt`).
  - Explicitly returns knowledge `gaps` if facts are not in the graph (e.g. unknown owners).
- **`get_service_brief(service)`**: Comprehensive ownership, dependency, incident, and runbook catalog.
- **`get_decision_context(decision)`**: Full Architecture Decision Record (ADR) history, motivation, and incident reviews.
- **`search_company_knowledge(query, entity_types=None, limit=10)`**: Entity discovery linked to source documentation.
- **`ingest_company_records(source, records, relationships)`**: Safe structured batch ingestion strictly restricted to company labels.

---

## 5. Shared Domain Core & Security Boundaries

### Security Invariants
1. **No `run_cypher` Tool**: Clients cannot run raw Cypher queries. All traversals are locked behind domain methods.
2. **Identity Isolation (No `user_id` in Tools)**:
   - Tool schemas **never accept `user_id`**.
   - `TrustedIdentity.current()` resolves identity server-side from configuration (`DEMO_USER_ID`).
   - Every Cypher memory query includes `user_id = $uid`.
   - Verified by unit tests introspecting all tool parameters via `test_mcp_tool_schemas.py`.
3. **Parameterization Only**: All user-supplied values are bound via `$params`. Label names, relationship types, and depth numbers cannot be parameterized in Cypher; they are strictly validated against token allowlists and integer bounds before interpolation.
4. **Secret Scanner**:
   - Scans all text payloads for sensitive patterns: `password=`, `api_key=`, `Bearer `, `sk-...`, `-----BEGIN RSA PRIVATE KEY-----`.
   - Calculates Shannon entropy on tokens ($> 4.2$ entropy over 32+ characters is rejected with `INVALID_INPUT`).
5. **No stdout Writes**: Standard output is reserved exclusively for JSON-RPC MCP framing. All application logs use a custom JSON formatter streaming to `stderr`.

---

## 6. FalkorDB Field Learnings & Opportunities for Improvement

During the development, integration, and live testing against **FalkorDB Cloud** (v4.22.0 / falkordb-py 1.8.0), several important nuances were discovered and adapted inside our adapter layer (`falkordb_client.py` and `service.py`). These represent high-value opportunities for FalkorDB engine and SDK enhancements:

### 1. Undirected `shortestPath()` Traversal Support
- **Current Behavior**: FalkorDB raises:
  `redis.exceptions.ResponseError: FalkorDB does not currently support undirected shortestPath traversals`
  when evaluating patterns such as `MATCH p = shortestPath((a)-[*..4]-(b))`.
- **Engine Adaptation**: Our platform implemented a bounded Breadth-First Search (BFS) in Python utilizing 1-hop neighbor queries (`MATCH (a {id: $id})-[r]-(b)`).
- **Recommendation for FalkorDB**: Native engine support for undirected shortest path traversals (standard openCypher compliance) would significantly improve performance and developer ergonomics for blast-radius and knowledge graph discovery queries.

### 2. Clause Flexibility for Path Functions
- **Current Behavior**: FalkorDB requires `shortestPath` to be used in `WITH` or `RETURN` clauses (`FalkorDB currently only supports shortestPaths in WITH or RETURN clauses`), disallowing `MATCH p = shortestPath(...)`.
- **Recommendation for FalkorDB**: Align `MATCH p = shortestPath(...)` with the openCypher specification to allow direct path assignment in `MATCH` statements.

### 3. Idempotent Index Creation (`IF NOT EXISTS`)
- **Current Behavior**: Executing `CREATE INDEX FOR (n:Service) ON (n.id)` when the index already exists raises:
  `Query attempt failed: Attribute 'id' is already indexed`
- **Adapter Adaptation**: `GraphStore.ensure_indexes()` queries `CALL db.indexes()` first to inspect existing indexes, and catches the `"already indexed"` string without resetting the connection.
- **Recommendation for FalkorDB**: Support `CREATE INDEX IF NOT EXISTS FOR (n:Label) ON (n.property)` so index creation can be fully declarative and idempotent.

### 4. Python SDK QueryResult Header Consistency
- **Current Behavior**: `QueryResult.header` in `falkordb-py` returns raw nested pairs `[[1, 'col_name']]` where index 0 is an internal type integer and index 1 is the column name (sometimes as raw bytes).
- **Adapter Adaptation**: Built an unpacker in `falkordb_client.py`:
  ```python
  col = h[1] if isinstance(h, (list, tuple)) and len(h) > 1 else h
  if isinstance(col, bytes):
      col = col.decode("utf-8")
  ```
- **Recommendation for FalkorDB SDK**: Provide a clean property `QueryResult.column_names: list[str]` or return rows directly as dictionaries via `QueryResult.to_dicts()`.

---

## 7. Verification & Test Suite (33/33 Passing)

The repository includes a comprehensive, multi-tiered test suite that runs against unit mocks, live FalkorDB Cloud instances, and live JSON-RPC stdio subprocesses:

```bash
.\.venv\Scripts\pytest.exe tests -v
```

### Test Results
```text
============================= test session starts =============================
platform win32 -- Python 3.14.0, pytest-9.1.1, pluggy-1.7.0
rootdir: /path/to/graph-intelligence-platform
configfile: pyproject.toml
plugins: anyio-4.15.1
collected 33 items

tests/integration/test_company_brain.py::test_answer_company_question_acceptance PASSED [  3%]
tests/integration/test_company_brain.py::test_get_service_brief PASSED   [  6%]
tests/integration/test_company_brain.py::test_get_decision_context PASSED [  9%]
tests/integration/test_company_brain.py::test_unknown_question_reports_gaps PASSED [ 12%]
tests/integration/test_memory.py::test_full_memory_lifecycle PASSED [ 15%]
tests/integration/test_reasoning.py::test_find_service_dependencies PASSED [ 18%]
tests/integration/test_reasoning.py::test_analyze_change_impact_paymentservice PASSED [ 21%]
tests/integration/test_reasoning.py::test_find_graph_path PASSED         [ 24%]
tests/integration/test_seed.py::test_seed_idempotency_and_verification PASSED [ 27%]
tests/mcp_smoke/test_stdio_servers.py::test_reasoning_server_stdio[asyncio] PASSED [ 30%]
tests/mcp_smoke/test_stdio_servers.py::test_memory_server_stdio[asyncio] PASSED [ 33%]
tests/mcp_smoke/test_stdio_servers.py::test_brain_server_stdio[asyncio] PASSED [ 36%]
tests/unit/test_demo_data_integrity.py::test_demo_data_counts PASSED     [ 39%]
tests/unit/test_demo_data_integrity.py::test_demo_data_schema_labels_and_edges PASSED [ 42%]
tests/unit/test_identity.py::test_trusted_identity_resolution PASSED     [ 45%]
tests/unit/test_mcp_tool_schemas.py::test_tool_counts PASSED             [ 48%]
tests/unit/test_mcp_tool_schemas.py::test_no_user_id_in_any_tool_schema PASSED [ 51%]
tests/unit/test_retrieval_scoring.py::test_scoring_weights PASSED        [ 54%]
tests/unit/test_retrieval_scoring.py::test_superseded_penalty PASSED     [ 57%]
tests/unit/test_retrieval_scoring.py::test_unrelated_query_scores_low PASSED [ 60%]
tests/unit/test_schema.py::test_allowed_labels PASSED                    [ 63%]
tests/unit/test_schema.py::test_company_vs_memory_isolation PASSED       [ 66%]
tests/unit/test_schema.py::test_allowed_relationships PASSED             [ 69%]
tests/unit/test_schema.py::test_validate_relationship_type PASSED        [ 72%]
tests/unit/test_text.py::test_normalize_term PASSED                      [ 75%]
tests/unit/test_text.py::test_squash PASSED                              [ 78%]
tests/unit/test_text.py::test_tokenize PASSED                            [ 81%]
tests/unit/test_text.py::test_extract_keywords PASSED                    [ 84%]
tests/unit/test_validation.py::test_scan_for_secrets_detects_patterns PASSED [ 87%]
tests/unit/test_validation.py::test_scan_for_secrets_clean_input PASSED  [ 90%]
tests/unit/test_validation.py::test_validate_text_length PASSED          [ 93%]
tests/unit/test_validation.py::test_validate_list_size PASSED            [ 96%]
tests/unit/test_validation.py::test_validate_int_range PASSED            [100%]

============================= 33 passed in 50.13s =============================
```

---

## 8. Live Demo Runbook & Prompt Storyboard

To provide a 100% leak-free, authentic demo where the AI assistant cannot read code files from the local directory:
1. Open a clean demo workspace (e.g. `./demo-workspace`).
2. It contains **only** [`.agent/rules/memory-policy.md`](.agent/rules/memory-policy.md) and zero source files.
3. The MCP servers communicate over stdio locally, or remotely via the hosted playground at **[https://graph-cortex.herbert.co.in](https://graph-cortex.herbert.co.in)**.

### Step 1: Corporate Brain (graphcortex-brain)
```text
Who owns PaymentService, which team are they on, why did GraphCortex choose idempotency keys, and which document supports that decision?
```
- **Observed Behavior**: Agent calls `answer_company_question`.
- **Returned Facts**: Maya Chen owns PaymentService (Payments team); ADR-014 was accepted to prevent duplicate charges during timeouts (`INC-PAY-019`); cites document `doc-adr-014` ("ADR-014 Idempotency Keys").

---

### Step 2: Blast Radius Reasoning (graphcortex-reasoning)
```text
If PaymentService changes its retry behavior, which services or features could be affected? Show the paths.
```
- **Observed Behavior**: Agent calls `analyze_change_impact`.
- **Returned Graph Facts**: Dependents (`API Gateway`), dependencies (`LedgerService`, `RiskEngine`, `NotificationService`), implemented features (`Bounded Retry Policy`, `Idempotent Payment Processing`), and governing decisions (`ADR-021`).

---

### Step 3: Session A — Memory Write (graphcortex-memory)
```text
We decided to use three Python MCP services over a shared FalkorDB graph. The memory service saves summaries per user and retrieves them in later sessions by topic. Save a concise summary of this session — the architecture decision, the reason, keywords, and next steps — so I can continue later.
```
- **Observed Behavior**: Agent calls `remember_session_summary`.
- **Result**: Summary persisted to FalkorDB; returns real `summary_id` (e.g. `sum_...`) with status `active` (version 1).

---

### Step 4: Session B — Cross-Session Retrieval in a Brand-New Conversation
> **Start a new conversation tab in Antigravity. Do NOT paste prior context.**

```text
I'm ready to implement the FalkorDB MCP memory feature. What architecture did we choose, and what were the next steps?
```
- **Observed Behavior**: Agent recognizes reference to prior decisions and invokes `search_user_memory`.
- **Result**: FalkorDB returns Session A's summary; agent answers with exact architecture decisions and next steps grounded in graph memory.

---

### Step 5: Session C — Versioned Memory Update
```text
Update that memory: the shared core is implemented, and the next task is to test retrieval ranking. Keep the original decision history.
```
- **Observed Behavior**: Agent calls `update_user_memory` (`update_type: "append_context"`).
- **Result**: Version 2 created; Version 1 marked `superseded` and linked via `(v2)-[:SUPERSEDES]->(v1)`.

---

## 9. Setup Instructions & Deployment Guide

This platform supports two primary deployment modes:
- **Option A: 100% Local Setup**: Run FalkorDB locally in Docker with zero cloud dependencies or external credentials required. Perfect for development, evaluation, and offline test verification.
- **Option B: Cloud Deployment**: Connect to a managed FalkorDB Cloud cluster for shared production deployments.

---

### Option A: 100% Local Setup (Docker + Local FalkorDB)

If you do not have a FalkorDB Cloud account or want to run everything locally without external infrastructure, follow these complete step-by-step instructions.

#### Prerequisites
- **Python 3.10+** (tested up to Python 3.14)
- **Docker & Docker Compose** (or Docker Desktop on Windows/macOS)
- **Git**

#### Step 1: Clone the Repository
```bash
git clone https://github.com/herbert-bevan/graph-cortex.git
cd graph-cortex
```

#### Step 2: Start Local FalkorDB via Docker
Run the official FalkorDB Docker container using the included `docker-compose.yml`:
```bash
docker compose up -d
```

*(Alternatively, run standalone without compose:)*
```bash
docker run -d --name graphcortex-falkordb -p 6379:6379 -v falkordb-data:/var/lib/falkordb/data falkordb/falkordb:latest
```

Verify that the container is healthy and listening on port `6379`:
```bash
docker ps --filter "name=graphcortex-falkordb"
```

#### Step 3: Set Up Python Virtual Environment & Dependencies

##### On Windows (PowerShell):
```powershell
# Create virtual environment
python -m venv .venv

# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Upgrade pip and install package with development/test dependencies
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

##### On Linux / macOS (Bash / Zsh):
```bash
# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate

# Upgrade pip and install package with development/test dependencies
pip install --upgrade pip
pip install -e ".[dev]"
```

#### Step 4: Configure Local `.env` File
Create a `.env` file in the repository root configured for your local Docker FalkorDB instance:

```dotenv
# Local FalkorDB Connection Settings (Docker)
FALKORDB_HOST=localhost
FALKORDB_PORT=6379
FALKORDB_USERNAME=
FALKORDB_PASSWORD=
FALKORDB_SSL=false

# Graph Names
FALKORDB_GRAPH=graphcortex_demo
FALKORDB_GRAPH_TEST=graphcortex_test

# Agent & Demo Context
DEMO_USER_ID=demo-user-dev
DEFAULT_PROJECT_ID=proj-payment-reliability
LOG_LEVEL=INFO
```

> **Note**: Local Docker FalkorDB requires no authentication by default. Leaving `FALKORDB_USERNAME` and `FALKORDB_PASSWORD` blank connects directly without credentials.

#### Step 5: Verify Connection to Local FalkorDB
```bash
# Windows
.\.venv\Scripts\python.exe scripts/check_connection.py

# Linux/macOS
python scripts/check_connection.py
```
**Expected Output:**
```text
Connecting to FalkorDB on localhost:6379...
[OK] Connected successfully to FalkorDB!
Graph 'graphcortex_demo' is ready.
```

#### Step 6: Seed Knowledge Graph & Schema
Populate the database with the synthetic enterprise graph (31 nodes, 53 relationships, and auto-generated indexes):
```bash
# Windows
.\.venv\Scripts\python.exe scripts/seed_demo.py

# Linux/macOS
python scripts/seed_demo.py
```

#### Step 7: Verify Database Seed State
```bash
# Windows
.\.venv\Scripts\python.exe scripts/verify_seed.py

# Linux/macOS
python scripts/verify_seed.py
```
**Expected Output:**
```text
Database contains 31 company nodes, 53 relationships, 2 user identity nodes, 0 initial summaries.
Schema indexes verified: 14 indexes active.
```

#### Step 8: Run Full Automated Test Suite
Execute all 33 unit tests, integration tests, and live MCP stdio subprocess tests against your local FalkorDB instance:
```bash
# Windows
.\.venv\Scripts\pytest.exe tests -v

# Linux/macOS
pytest tests -v
```
All 33 tests will pass with `[100%]` green status in under 60 seconds.

---

### Option B: Cloud Setup (FalkorDB Cloud)

To connect to a managed FalkorDB Cloud database:

1. Create a database instance on [FalkorDB Cloud](https://app.falkordb.com/).
2. Obtain your instance host, port, and password from the FalkorDB dashboard.
3. Update your `.env` file:
   ```dotenv
   FALKORDB_HOST=your-instance.cloud.falkordb.com
   FALKORDB_PORT=6379
   FALKORDB_USERNAME=falkordb
   FALKORDB_PASSWORD=your-cloud-password
   FALKORDB_SSL=false
   FALKORDB_GRAPH=graphcortex_demo
   FALKORDB_GRAPH_TEST=graphcortex_test
   DEMO_USER_ID=demo-user-dev
   DEFAULT_PROJECT_ID=proj-payment-reliability
   LOG_LEVEL=INFO
   ```
4. Run `python scripts/check_connection.py` followed by `python scripts/seed_demo.py`.

---

### Option C: Fully Containerized App

You can also run both FalkorDB and the Python MCP services together using Docker:

```bash
# Build the application image
docker build -t graphcortex-mcp-server .

# Start containers
docker compose up -d
```

---

### Option D: Remote Production VPS Deployment (Host Nginx + GitHub CI/CD)

For hosting a 24/7 public MCP endpoint for Claude Desktop, Cursor, and Antigravity over HTTPS with guest sandboxing:

1. **Repository Deployment Path on VPS**:
   ```bash
   mkdir -p /opt/graph-cortex
   cd /opt/graph-cortex
   git clone https://github.com/herbert-bevan/graph-cortex.git
   cd /opt/graph-cortex/graph-cortex
   ```

2. **Configure Production `.env`**:
   ```bash
   cd /opt/graph-cortex/graph-cortex
   cp .env.example .env
   # Set your DOMAIN_NAME, FALKORDB_PASSWORD, and DATABASE_URL
   ```

3. **Launch the Container Stack**:
   ```bash
   cd /opt/graph-cortex/graph-cortex
   docker compose up -d --build
   ```

4. **Nginx Reverse Proxy & SSL**:
   Route traffic from your existing Nginx web server to `127.0.0.1:8000` with `proxy_buffering off;` using [`scripts/nginx_graph_cortex.conf`](scripts/nginx_graph_cortex.conf).


---

### Testing Locally with MCP Inspector (`@modelcontextprotocol/inspector`)

The official [Model Context Protocol Inspector](https://github.com/modelcontextprotocol/inspector) (`@modelcontextprotocol/inspector`) allows you to interactively test, inspect, and debug any of the three MCP servers locally without needing to spin up an AI client or configure Claude Desktop.

You can run it in two modes:
1. **Interactive Web UI**: Launches a browser GUI on `http://localhost:5173` with visual form fields for all tool schemas, parameter validation, and real-time JSON-RPC inspector logs.
2. **Headless / CLI Mode (`--cli`)**: Directly queries tools, inspects schemas, and executes tool calls straight from your terminal.

#### Prerequisites
- Node.js 18+ installed (`node --version`)
- Python virtual environment created and dependencies installed (`pip install -e .`)
- FalkorDB running (either local Docker or FalkorDB Cloud)

> [!IMPORTANT]
> **Windows PowerShell Execution**:
> In Windows PowerShell, executing `npx` may trigger a `PSSecurityException` script execution error. Always use `npx.cmd` in PowerShell on Windows. On macOS and Linux, use standard `npx`.

---

#### Mode 1: Interactive Web UI Mode

Run any of the following commands in your terminal from the project root. The Inspector will launch a proxy process and automatically open your default browser to `http://localhost:5173`:

##### 1. Inspect Reasoning Engine: `graphcortex-reasoning`
```bash
# Windows (PowerShell)
npx.cmd @modelcontextprotocol/inspector .\.venv\Scripts\python.exe -m graph_intelligence.reasoning.mcp_server

# Linux / macOS
npx @modelcontextprotocol/inspector .venv/bin/python -m graph_intelligence.reasoning.mcp_server
```

##### 2. Inspect Autonomous Memory Engine: `graphcortex-memory`
> [!NOTE]
> `graphcortex-memory` isolates user memory using server-side identity injection. When launching via MCP Inspector, supply the test user identity via the `-e` environment flag:

```bash
# Windows (PowerShell)
npx.cmd @modelcontextprotocol/inspector -e DEMO_USER_ID=demo-user-dev .\.venv\Scripts\python.exe -m graph_intelligence.memory.mcp_server

# Linux / macOS
npx @modelcontextprotocol/inspector -e DEMO_USER_ID=demo-user-dev .venv/bin/python -m graph_intelligence.memory.mcp_server
```

##### 3. Inspect Corporate Knowledge Brain: `graphcortex-brain`
```bash
# Windows (PowerShell)
npx.cmd @modelcontextprotocol/inspector .\.venv\Scripts\python.exe -m graph_intelligence.company_brain.mcp_server

# Linux / macOS
npx @modelcontextprotocol/inspector .venv/bin/python -m graph_intelligence.company_brain.mcp_server
```

Once the Web UI opens:
- Click **"List Tools"** to view all registered tools, descriptions, and required argument types.
- Select a tool (e.g. `find_service_dependencies`), populate the input fields, and click **"Run Tool"**.
- View the exact returned JSON envelope and inspect the raw `stderr` JSON telemetry in the inspector console pane.

---

#### Mode 2: Headless / CLI Mode (`--cli`)

For rapid automated checks and scripts, use the `--cli` flag:

##### 1. List Available Tools
```bash
# Windows (PowerShell)
npx.cmd @modelcontextprotocol/inspector --cli --method tools/list .\.venv\Scripts\python.exe -m graph_intelligence.reasoning.mcp_server
```
**Sample Output:**
```json
{
  "tools": [
    {
      "name": "find_service_dependencies",
      "description": "Find upstream dependencies or downstream dependents of a service in the GraphCortex graph.",
      "inputSchema": { ... }
    },
    {
      "name": "analyze_change_impact",
      "description": "Analyze the cascading blast radius and change impact of modifying a service, feature, or architecture decision.",
      "inputSchema": { ... }
    }
  ]
}
```

##### 2. Execute a Reasoning Tool via CLI
> [!TIP]
> **PowerShell JSON Quoting**: When passing JSON via `--tool-args-json` in PowerShell to `npx.cmd`, escape internal quotes using backslashes `\"` (or PowerShell backticks `` `\" ``):
> ```powershell
> --tool-args-json '{\"service\":\"PaymentService\",\"direction\":\"both\",\"max_depth\":2}'
> ```
> For complex payloads or strings containing spaces, the **Interactive Web UI** (`http://localhost:5173`) provides visual input forms with automatic JSON formatting.

```bash
# Windows (PowerShell)
npx.cmd @modelcontextprotocol/inspector --cli --method tools/call --tool-name find_service_dependencies --tool-args-json '{\"service\":\"PaymentService\",\"direction\":\"both\",\"max_depth\":2}' .\.venv\Scripts\python.exe -m graph_intelligence.reasoning.mcp_server

# Linux / macOS
npx @modelcontextprotocol/inspector --cli --method tools/call --tool-name find_service_dependencies --tool-args-json '{"service":"PaymentService","direction":"both","max_depth":2}' .venv/bin/python -m graph_intelligence.reasoning.mcp_server
```

##### 3. Execute a Memory Write via CLI
```bash
# Windows (PowerShell)
npx.cmd @modelcontextprotocol/inspector --cli -e DEMO_USER_ID=demo-user-dev --method tools/call --tool-name remember_session_summary --tool-args-json '{\"title\":\"CLI_Summary\",\"summary\":\"Tested_persistence_via_inspector_CLI\",\"keywords\":[\"inspector\",\"test\",\"cli\"],\"entities\":[\"PaymentService\"]}' .\.venv\Scripts\python.exe -m graph_intelligence.memory.mcp_server
```

##### 4. Execute a Memory Search via CLI
```bash
# Windows (PowerShell)
npx.cmd @modelcontextprotocol/inspector --cli -e DEMO_USER_ID=demo-user-dev --method tools/call --tool-name search_user_memory --tool-args-json '{\"query\":\"cli\",\"keywords\":[\"inspector\"]}' .\.venv\Scripts\python.exe -m graph_intelligence.memory.mcp_server
```

---

### Configuring MCP Clients

The three MCP servers communicate using the JSON-RPC stdio protocol. Configure your preferred AI client:

#### 1. Google Antigravity
Add the following to your Antigravity MCP configuration (`MCP Servers -> Manage MCP Servers -> View raw config`):

```json
{
  "mcpServers": {
    "graphcortex-reasoning": {
      "command": "/absolute/path/to/falkordb-graph-intelligence/.venv/Scripts/python.exe",
      "args": ["-m", "graph_intelligence.reasoning.mcp_server"]
    },
    "graphcortex-memory": {
      "command": "/absolute/path/to/falkordb-graph-intelligence/.venv/Scripts/python.exe",
      "args": ["-m", "graph_intelligence.memory.mcp_server"],
      "env": {
        "DEMO_USER_ID": "demo-user-dev"
      }
    },
    "graphcortex-brain": {
      "command": "/absolute/path/to/falkordb-graph-intelligence/.venv/Scripts/python.exe",
      "args": ["-m", "graph_intelligence.company_brain.mcp_server"]
    }
  }
}
```
*(On Linux/macOS, replace `.venv/Scripts/python.exe` with `.venv/bin/python`)*

#### 2. Claude Desktop (`claude_desktop_config.json`)
```json
{
  "mcpServers": {
    "graphcortex-reasoning": {
      "command": "python",
      "args": ["-m", "graph_intelligence.reasoning.mcp_server"],
      "cwd": "/path/to/falkordb-graph-intelligence"
    },
    "graphcortex-memory": {
      "command": "python",
      "args": ["-m", "graph_intelligence.memory.mcp_server"],
      "cwd": "/path/to/falkordb-graph-intelligence",
      "env": { "DEMO_USER_ID": "demo-user-dev" }
    },
    "graphcortex-brain": {
      "command": "python",
      "args": ["-m", "graph_intelligence.company_brain.mcp_server"],
      "cwd": "/path/to/falkordb-graph-intelligence"
    }
  }
}
```

---

### Local Troubleshooting & Diagnostic Guide

| Issue | Cause | Fix |
|---|---|---|
| `redis.exceptions.ConnectionError: Error 10061 connecting to localhost:6379` | Local FalkorDB container is not running. | Run `docker compose up -d` or `docker start graphcortex-falkordb`. Verify with `docker ps`. |
| `Address already in use: 6379` | Existing local Redis or FalkorDB process occupies port 6379. | Stop the existing service (`sudo systemctl stop redis` on Linux or stop via Windows Services / Docker), or map to a different host port in `docker-compose.yml` (e.g. `"6380:6379"` and set `FALKORDB_PORT=6380` in `.env`). |
| `PSSecurityException: File ... Activate.ps1 cannot be loaded` | Windows PowerShell execution policy blocks scripts. | Run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in your PowerShell terminal before running `.\.venv\Scripts\Activate.ps1`. |
| `JSONRPCError / Protocol Desynchronization` | Server wrote stdout text instead of clean JSON-RPC messages. | Ensure no `print()` statements are added to MCP code. All logging in this repository strictly outputs JSON to `stderr`. |
| `Attribute 'id' is already indexed` | Non-idempotent index creation. | Handled automatically by `GraphStore.ensure_indexes()`. If manually modifying schema, inspect with `CALL db.indexes()` first. |

---

## 10. Deep Architecture & File-by-File Code Flow

For an in-depth architectural and code-level walkthrough, please refer to the comprehensive reference document:

📖 **[ARCHITECTURE_CODE_FLOW.md](ARCHITECTURE_CODE_FLOW.md)**

### Key Highlights Covered in the Deep Dive:
- **Clean / Hexagonal Architecture**: Complete decoupling of stdio transports, domain services, and database adapters.
- **Component Breakdown**:
  - `src/graph_intelligence/common/`: Driver isolation ([`GraphStore`](src/graph_intelligence/common/falkordb_client.py)), zero-stdout structured logging ([`logging_setup.py`](src/graph_intelligence/common/logging_setup.py)), secret scanner & bounds ([`validation.py`](src/graph_intelligence/common/validation.py)), and trusted caller identity ([`identity.py`](src/graph_intelligence/common/identity.py)).
  - `src/graph_intelligence/reasoning/`: Directed graph traversal queries ([`queries.py`](src/graph_intelligence/reasoning/queries.py)), blast radius calculation & risk scoring ([`service.py`](src/graph_intelligence/reasoning/service.py)).
  - `src/graph_intelligence/memory/`: Persistent session versioning (`[:SUPERSEDES]`), 8-stage deterministic scoring formula ([`retrieval.py`](src/graph_intelligence/memory/retrieval.py)), and read-back verification ([`service.py`](src/graph_intelligence/memory/service.py)).
  - `src/graph_intelligence/company_brain/`: 60-second TTL cached entity resolver ([`resolver.py`](src/graph_intelligence/company_brain/resolver.py)), grounded source-backed Q&A with gap detection ([`service.py`](src/graph_intelligence/company_brain/service.py)), and idempotent ingestion ([`ingestion.py`](src/graph_intelligence/company_brain/ingestion.py)).
- **4 Complete Sequence Diagrams**: Step-by-step traces for blast radius analysis, memory write, memory search, and company Q&A.
- **Design Patterns & Defense-in-Depth Rationale**: Detailed explanations for why each file exists as an independent layer to maximize testability, security, and maintainability.

