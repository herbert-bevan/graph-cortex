# The Complete VPS, Nginx, Cloudflare & CI/CD Deployment Guide

This guide explains **every single component** of the deployment in plain English, why it exists, and provides a foolproof, step-by-step walkthrough to get your FalkorDB Graph Intelligence platform live on your VPS using your **existing Nginx web server** with automatic HTTPS and continuous deployment.

---

## Table of Contents

1. [Do We Need the Demo Runbook & Seed Scripts?](#1-do-we-need-the-demo-runbook--seed-scripts)
2. [The Architecture in Plain English (What & Why)](#2-the-architecture-in-plain-english-what--why)
   - [What is a VPS?](#what-is-a-vps)
   - [What is DNS & Subdomain?](#what-is-dns--subdomain)
   - [Using Your Existing Nginx (And Why SSE Streaming Directives Matter)](#using-your-existing-nginx-and-why-sse-streaming-directives-matter)
   - [What is Cloudflare? (DNS, DDoS Protection & Turnstile)](#what-is-cloudflare-dns-ddos-protection--turnstile)
   - [What is Docker & Docker Compose?](#what-is-docker--docker-compose)
   - [What is PostgreSQL's Role?](#what-is-postgresqls-role)
   - [What is FalkorDB's Role?](#what-is-falkordbs-role)
   - [What is GitHub Actions CI/CD?](#what-is-github-actions-cicd)
3. [Step-by-Step Deployment Walkthrough](#3-step-by-step-deployment-walkthrough)
   - [Step 1: Point Your Subdomain to Your VPS IP (DNS)](#step-1-point-your-subdomain-to-your-vps-ip-dns)
   - [Step 2: Clone Repo & Configure Secrets on VPS](#step-2-clone-repo--configure-secrets-on-vps)
   - [Step 3: Launch Docker Stack & Seed FalkorDB](#step-3-launch-docker-stack--seed-falkordb)
   - [Step 4: Configure Your Existing Host Nginx](#step-4-configure-your-existing-host-nginx)
   - [Step 5: Get Free SSL with Certbot](#step-5-get-free-ssl-with-certbot)
   - [Step 6: Configure GitHub Actions CI/CD (Zero-Touch Deploys)](#step-6-configure-github-actions-cicd-zero-touch-deploys)
   - [Step 7: (Optional) Enable Cloudflare Proxy & Turnstile CAPTCHA](#step-7-optional-enable-cloudflare-proxy--turnstile-captcha)
4. [Verification Checklist](#4-verification-checklist)

---

## 1. Do We Need the Demo Runbook & Seed Scripts?

### 1.1 `DEMO_RUNBOOK.md` & `ANTIGRAVITY_DEMO_INSTRUCTIONS.md`
**Verdict: DELETED.**
* `DEMO_RUNBOOK.md` was written as a timed storyboard for recording video demos (*"Minute 0:00 - 1:00 Introduction..."*).
* In a professional, public open-source repository or deployed product, a demo script looks amateurish and signals "hackathon prototype". 
* The clean engine documentation belongs in `README.md` and `ARCHITECTURE_CODE_FLOW.md`. Both runbooks have been deleted.

### 1.2 Database Seeding & Clean Start
**Verdict: 100% Zero-Touch Autonomous Startup.**
* You do not need to run any manual seed or migration scripts during deployment.
* FalkorDB schema indexes and PostgreSQL tables are automatically verified and created on startup by the application lifespan handler.
* The system boots clean and is immediately ready to store and retrieve user memories, decisions, and tasks.

---

## 2. The Architecture in Plain English (What & Why)

Here is a visual map of how an incoming request travels from an AI agent to your server:

```mermaid
flowchart TD
  User["LinkedIn User / AI Agent<br/>(Claude Desktop / Cursor / Antigravity)"]
  
  subgraph Cloudflare_Layer["1. Cloudflare Edge (Optional)"]
    CF["Cloudflare DNS & Turnstile<br/>(Hides VPS IP + Blocks Bots)"]
  end

  subgraph VPS_Host["2. Your Linux VPS Host"]
    Nginx["3. Your Existing Nginx<br/>(:80, :443)<br/>(SSL Termination + SSE Streaming)"]
    
    subgraph Docker_Network["Docker Stack (Private to Host)"]
      App["4. FastAPI + FastMCP Server<br/>(127.0.0.1:8000)<br/>Web UI + MCP SSE Protocol"]
      PG[("5. PostgreSQL 16<br/>(:5432)<br/>Guest Tokens, Quotas (10 sessions), TTL")]
      Falkor[("6. FalkorDB<br/>(:6379)<br/>Company Brain + Sandboxed User Memories")]
    end
  end

  User -->|HTTPS Request| CF
  CF -->|Encrypted Traffic| Nginx
  Nginx -->|Internal proxy to 127.0.0.1:8000| App
  App -->|Validate Token & Deduct Quota| PG
  App -->|Graph Traversal & Scoped Memory| Falkor
```

### What is a VPS?
* **What it is**: A virtual computer running Linux (usually Ubuntu) in a cloud datacenter (like Hetzner, DigitalOcean, Linode, or AWS) that stays powered on 24 hours a day, 7 days a week, with a dedicated public IP address.
* **Why we need it**: If you hosted the demo on your laptop, the MCP server would go offline the moment you closed your laptop lid or put it to sleep. The VPS ensures anyone reading your LinkedIn post in any timezone can test the agent at 3:00 AM.

---

### What is DNS & Subdomain?
* **What it is**: The phonebook of the internet. A domain is `yourdomain.com`. A subdomain is a prefix, like `demo.yourdomain.com` or `mcp.yourdomain.com`. An **A-Record** simply tells the internet: *"Whenever someone types `demo.yourdomain.com`, send them to IP `123.45.67.89`."*
* **Why we need it**: AI agent clients (Claude Desktop, Antigravity) and web browsers require **HTTPS** (encrypted connections). You cannot get a trusted, free SSL certificate for a raw IP address — you need a domain name.

---

### Using Your Existing Nginx (And Why SSE Streaming Directives Matter)
* **What it is**: You already have Nginx running on your VPS handling your other domains or applications.
* **How we use it**:
  * Instead of installing another web server, Docker exposes our app privately on `127.0.0.1:8000`.
  * Your host Nginx handles `demo.yourdomain.com` on port 80/443 and forwards traffic to `127.0.0.1:8000`.
* **CRITICAL NGINX SETTING FOR MCP**:
  * Model Context Protocol (MCP) uses **Server-Sent Events (SSE)**.
  * By default, Nginx **buffers** incoming responses in memory before sending them to the client. This breaks streaming! In Claude Desktop or Antigravity, the LLM will hang and wait forever.
  * In our Nginx config ([`scripts/nginx_graph_cortex.conf`](scripts/nginx_graph_cortex.conf)), we include:
    ```nginx
    proxy_buffering off;
    proxy_cache off;
    proxy_set_header Connection '';
    proxy_http_version 1.1;
    chunked_transfer_encoding off;
    proxy_read_timeout 86400s;
    ```
    This tells Nginx: *"Do not buffer packets; stream every single byte immediately as the agent writes it."*

---

### What is Cloudflare? (DNS, DDoS Protection & Turnstile)
* **What it is**: A massive network that sits between the public internet and your VPS.
* **Why we need it**:
  1. **Hides your VPS IP**: If Cloudflare's orange cloud (Proxy) is ON, hackers only see Cloudflare's IP addresses, not your personal VPS IP.
  2. **DDoS & Bot Shield**: Blocks automated scanners and script kiddies before they ever touch your server.
  3. **Cloudflare Turnstile**: A modern, invisible CAPTCHA. It stops bot scripts from repeatedly calling `/api/guest` to generate thousands of tokens, while human users on LinkedIn never have to solve annoying image puzzles.

---

### What is Docker & Docker Compose?
* **What it is**: Containerization technology. It wraps software into self-contained "containers" that include everything needed to run: code, runtime, system libraries, and settings.
* **Why we need it**:
  * You don't have to manually install Python 3.12, PostgreSQL 16, or FalkorDB directly on your VPS.
  * You run **one single command** (`docker compose up -d`), and Docker spins up the app, FalkorDB, and Postgres, linking them across an isolated private network.
  * If a container crashes, Docker automatically restarts it.
  * Databases are private: PostgreSQL (5432) and FalkorDB (6379) are **never exposed** to the public internet — only your local application container can reach them.

---

### What is PostgreSQL's Role?
* **What it is**: An enterprise relational SQL database.
* **Why we need it**: It acts as the **Bouncer and Quota Engine**:
  * When a user visits the web portal, Postgres creates their guest token.
  * It tracks: *"User Alex has used 3 out of 10 sessions"*.
  * It enforces: *"This token was created 23 hours ago; in 1 hour it will be deleted"*.
  * It rate-limits: *"This IP address already created 3 guest tokens this hour; block further creations"*.

---

### What is FalkorDB's Role?
* **What it is**: An ultra-low latency Graph Database built on Redis graph technology.
* **Why we need it**: It is the core intelligence engine:
  * Stores the **Corporate Knowledge Graph** (Services, ADRs, Incidents, Dependencies).
  * Stores **User Long-Term Memory** (`SessionSummary` nodes, decision logs, and open tasks).
  * Executes Cypher queries and blast-radius traversals without needing slow or hallucination-prone vector embeddings.

---

### What is GitHub Actions CI/CD?
* **What it is**: Continuous Integration & Continuous Deployment. An automated robot hosted by GitHub.
* **Why we need it**:
  * Without CI/CD: Every time you fix a bug, you have to open an SSH terminal, navigate folders, run git pull, rebuild Docker, and restart services manually.
  * With CI/CD: You simply write code on your laptop and run `git push origin main`. GitHub Actions wakes up, runs your unit tests, connects to your VPS over SSH, pulls the latest code, and reloads the Docker containers with zero downtime.

---

## 3. Step-by-Step Deployment Walkthrough

Follow these exact steps in order:

### Step 1: Point Your Subdomain to Your VPS IP (DNS)
1. Log in to where your domain is managed (e.g. Cloudflare, Namecheap, GoDaddy, Hostinger).
2. Go to **DNS Records** -> **Add Record**.
3. Fill in:
   * **Type**: `A`
   * **Name**: `demo` (or `mcp`, which results in `demo.yourdomain.com`)
   * **IPv4 Address**: `YOUR_VPS_IP` (e.g. `123.45.67.89`)
   * **Proxy status**: Start with **DNS only** (Grey cloud) during initial SSL cert generation. You can turn on the Orange cloud later.
   * **TTL**: `Auto` or `5 minutes`.
4. Test that the record works from your local terminal:
   ```bash
   ping demo.yourdomain.com
   ```
   *(It should show your VPS IP).*

---

### Step 2: Clone Repo & Configure Secrets on VPS

SSH into your VPS as `root` or a `sudo` user:
```bash
ssh root@YOUR_VPS_IP
```

Create the deployment folder and clone your repository:
```bash
mkdir -p /opt/graph-cortex
cd /opt/graph-cortex

# Clone your repository
git clone https://github.com/herbert-bevan/graph-cortex.git
cd /opt/graph-cortex/graph-cortex
```

Now, create your production `.env` file inside the cloned directory:
```bash
cp .env.example .env
nano .env
```

Set the values in `.env`:
```bash
# 1. Your Domain Name
DOMAIN_NAME=demo.yourdomain.com

# 2. FalkorDB Settings (Create a strong password)
FALKORDB_HOST=falkordb
FALKORDB_PORT=6379
FALKORDB_PASSWORD=your_falkordb_password
FALKORDB_GRAPH=graphcortex

# 3. PostgreSQL Settings (Create a strong password)
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_postgres_password
POSTGRES_DB=graphcortex
DATABASE_URL=postgresql://postgres:your_postgres_password@your_postgres_host:5432/graphcortex

# 4. Quotas & Protections
MAX_CONCURRENT_GUESTS=50
GUEST_SESSION_LIMIT=10
GUEST_TTL_HOURS=24
```
Save and exit `nano` (`CTRL+O`, `ENTER`, `CTRL+X`).

---

### Step 3: Launch Docker Stack & Seed FalkorDB

Start the backend containers (App on `127.0.0.1:8000`, FalkorDB):
```bash
cd /opt/graph-cortex/graph-cortex
docker compose up -d --build
```

Check that all containers are running:
```bash
docker compose ps
```
You should see:
* `graphcortex-mcp-server` (Up, listening on `127.0.0.1:8000`)
* `graphcortex-falkordb` (Up, internal port 6379)
* `graphcortex-postgres` (Up, healthy, internal port 5432)

> [!NOTE]
> **Zero-Touch Startup**:
> You do not need to run any manual migration or seed commands.
> GraphCortex automatically verifies and initializes PostgreSQL tables and FalkorDB schema indexes on startup via the application lifespan handler.

### Step 4: Configure Your Existing Host Nginx

Now configure your existing Nginx on the VPS to route `demo.yourdomain.com` to `127.0.0.1:8000`:

1. Copy the ready-made Nginx config from the repo:
   ```bash
   cp /opt/graph-cortex/graph-cortex/scripts/nginx_graph_cortex.conf /etc/nginx/sites-available/graph-cortex
   ```

2. Edit `/etc/nginx/sites-available/graph-cortex` to put your actual domain name:
   ```bash
   nano /etc/nginx/sites-available/graph-cortex
   ```
   Change line 8:
   ```nginx
   server_name demo.yourdomain.com;
   ```
   Save and exit (`CTRL+O`, `ENTER`, `CTRL+X`).

3. Enable the site and reload Nginx:
   ```bash
   ln -s /etc/nginx/sites-available/graph-cortex /etc/nginx/sites-enabled/
   nginx -t
   systemctl reload nginx
   ```

---

### Step 5: Get Free SSL with Certbot

Run `certbot` to issue your SSL certificate:
```bash
certbot --nginx -d demo.yourdomain.com
```
Certbot will verify your domain, update your Nginx configuration with HTTPS certificates automatically, and set up HTTP -> HTTPS redirection.

Now open your web browser and visit:
👉 **`https://demo.yourdomain.com`**

You will see the dark-mode GraphCortex guest portal with a valid SSL lock!

---

### Step 6: Configure GitHub Actions CI/CD (Zero-Touch Deploys)

To make future updates deploy automatically when you run `git push origin main`:

#### 1. Generate an SSH Keypair on your VPS:
On your VPS:
```bash
ssh-keygen -t ed25519 -C "github-actions-deploy" -f /root/.ssh/github_actions -N ""
cat /root/.ssh/github_actions.pub >> /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
```

Display the private key:
```bash
cat /root/.ssh/github_actions
```
*(Copy the entire output starting with `-----BEGIN OPENSSH PRIVATE KEY-----`)*

#### 2. Add Secrets to GitHub:
1. Open your GitHub Repository in your browser.
2. Go to **Settings** ➔ **Secrets and variables** ➔ **Actions**.
3. Click **New repository secret** and add:
   * **`VPS_HOST`**: Your VPS public IP address (e.g. `123.45.67.89`).
   * **`VPS_USER`**: `root` (or your sudo username).
   * **`VPS_SSH_KEY`**: Paste the private key content you just copied.

#### 3. Test the Automation:
Make any small change in your repository on your laptop and run:
```bash
git add .
git commit -m "feat: test automated CI/CD deployment"
git push origin main
```
Go to the **Actions** tab on your GitHub repository. You will see:
1. Unit tests execute and pass (`pytest tests/unit`).
2. GitHub Actions connects to your VPS via SSH.
3. It runs `git pull`, rebuilds the Docker container, and restarts services seamlessly!

---

### Step 7: (Optional) Enable Cloudflare Proxy & Turnstile CAPTCHA

Once your SSL certificate is working with Nginx:
1. **Turn on Cloudflare Proxy**:
   In your Cloudflare DNS panel, toggle the cloud icon next to `demo` to **Orange (Proxied)**.
   * In Cloudflare **SSL/TLS Settings**, set encryption mode to **Full (Strict)**.
   * Your VPS IP is now completely concealed from the world.
2. **Cloudflare Turnstile (Anti-Bot)**:
   * Go to Cloudflare Dashboard ➔ **Turnstile** ➔ **Add Widget**.
   * Add domain `demo.yourdomain.com` and select **Managed** (invisible).
   * Put the `Site Key` in your HTML template (`server.py`).
   * Now, automated bot scripts can never spam your guest token generator!

---

## 4. Verification Checklist

Before publishing your LinkedIn post, test this 2-minute verification loop:

- [ ] **Web Portal**: Visit `https://demo.yourdomain.com` in your browser. Enter a test name (e.g. `DevTest`) and click **Generate 1-Click Agent Access Token**.
- [ ] **Config Output**: Confirm that a valid JSON snippet with an active bearer token appears.
- [ ] **Connect Claude Desktop / Antigravity**:
  Paste the snippet into your MCP client config:
  ```json
  {
    "mcpServers": {
      "graph-cortex": {
        "url": "https://demo.yourdomain.com/sse",
        "headers": {
          "Authorization": "Bearer key_YOUR_GENERATED_TOKEN"
        }
      }
    }
  }
  ```
- [ ] **Test Knowledge Q&A**: Ask the agent: *"Who owns PaymentService and why did GraphCortex choose idempotency keys?"* (Verifies read-only corporate brain).
- [ ] **Test Cross-Session Memory**: Ask the agent: *"Save a summary: we decided to implement JWT authentication for billing."* (Verifies sandboxed FalkorDB memory write).
- [ ] **Open a New Conversation**: In a fresh conversation with no context, ask: *"What did we decide for billing?"* (Verifies deterministic memory recall!).

You are now 100% production-ready for your LinkedIn launch!### 1.2 Database Seeding & Clean Start
**Verdict: 100% Zero-Touch Autonomous Startup.**
* You do not need to run any manual seed or migration scripts during deployment.
* FalkorDB schema indexes and PostgreSQL tables are automatically verified and created on startup by the application lifespan handler.
* The system boots clean and is immediately ready to store and retrieve user memories, decisions, and tasks.

---


