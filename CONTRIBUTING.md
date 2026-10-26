# Contributing to GraphCortex

Thank you for your interest in contributing to **GraphCortex**! We welcome bug reports, documentation enhancements, feature proposals, and pull requests.

## Code of Conduct

Please be respectful, collaborative, and constructive when interacting with maintainers and other contributors.

---

## Development Setup

### 1. Prerequisites
- **Python 3.10+** (Python 3.12+ recommended)
- **Git**
- **Docker & Docker Compose** (for running local FalkorDB)

### 2. Fork and Clone
```bash
git clone https://github.com/<your-username>/graph-cortex.git
cd graph-cortex
```

### 3. Create a Virtual Environment
```bash
# On Linux / macOS
python3 -m venv .venv
source .venv/bin/activate

# On Windows
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 4. Install Dependencies
Install the package in editable mode with development dependencies:
```bash
pip install -e ".[dev]"
```

### 5. Configure Local Environment
Copy the example environment file:
```bash
cp .env.example .env
```
For local development, the defaults in `.env.example` connect to local FalkorDB at `localhost:6379`.

---

## Running FalkorDB Locally

Start FalkorDB in Docker:
```bash
docker compose up -d
```
Verify the connection and seed the enterprise architecture graph:
```bash
python scripts/check_connection.py
python scripts/seed_demo.py
python scripts/verify_seed.py
```

---

## Architectural & Security Conventions

1. **Clean Hexagonal Architecture**:
   - `src/graph_intelligence/common/`: Driver adapters, schema allowlists, validation, text normalization.
   - `src/graph_intelligence/reasoning/`: Architectural blast radius & dependency services.
   - `src/graph_intelligence/memory/`: Deterministic, non-vector user memory services.
   - `src/graph_intelligence/company_brain/`: Fact-backed company knowledge Q&A services.
   - `src/graph_intelligence/remote/`: FastAPI remote MCP server, guest token sandbox, and Web portal.

2. **Zero-Stdout Inviolability**:
   - The MCP stdio transport requires strict silence on `stdout`. Any non-protocol output corrupts JSON-RPC framing.
   - Never use `print()` in production server code. Always use `get_logger()` from `graph_intelligence.common.logging_setup`, which outputs structured JSON to `stderr`.

3. **Tenant Isolation & Security**:
   - Never expose `user_id` as a client argument in MCP tool signatures.
   - Always resolve user identity server-side using `TrustedIdentity` or the remote authenticated guest context.
   - All Cypher queries must be parameterized. Never assemble Cypher strings via direct string formatting.
   - Pass user-provided text through `scan_for_secrets()`.

4. **Status & Diagnostics API Security**:
   - Public health endpoints (e.g. `/api/status`) must return only high-level readiness statuses.
   - Never expose internal hostnames, IP addresses, database paths, connection URLs, or raw exception strings in public API responses.

---

## Testing & Verification

Before submitting a pull request, ensure all tests pass:

```bash
# Run unit and schema integrity tests
pytest tests/unit -v

# Run the complete test suite (requires local FalkorDB running)
pytest tests -v
```

---

## Submitting Pull Requests

1. Create a feature branch: `git checkout -b feature/my-new-feature`.
2. Commit your changes with clear, descriptive commit messages following Conventional Commits (e.g. `feat(memory): ...`, `fix(security): ...`, `docs: ...`).
3. Ensure all tests and linting pass locally.
4. Push your branch to GitHub and open a Pull Request against `main`.
5. Maintainers will review your submission and provide feedback.
