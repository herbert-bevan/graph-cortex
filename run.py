#!/usr/bin/env python3
"""
Unified Developer Runner for FalkorDB Graph Intelligence Platform.
Equivalent to 'dotnet run' in the .NET ecosystem.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent

# Ensure Python virtual environment executable is prioritized
if sys.platform == "win32":
    VENV_PYTHON = ROOT_DIR / ".venv" / "Scripts" / "python.exe"
    NPX_CMD = "npx.cmd"
else:
    VENV_PYTHON = ROOT_DIR / ".venv" / "bin" / "python"
    NPX_CMD = "npx"

PYTHON_EXEC = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable


def run_command(cmd, env=None, cwd=ROOT_DIR):
    """Run a shell command forwarding stdout/stderr."""
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(cmd, env=merged_env, cwd=cwd)


def launch_inspector(server_module: str, extra_env=None):
    """Launch Model Context Protocol Inspector Web UI."""
    print(f"\n[INFO] Starting MCP Inspector for {server_module}...")
    print(f"[INFO] Opening browser UI on http://localhost:5173\n")
    cmd = [NPX_CMD, "@modelcontextprotocol/inspector"]
    if extra_env:
        for k, v in extra_env.items():
            cmd.extend(["-e", f"{k}={v}"])
    cmd.extend([PYTHON_EXEC, "-m", server_module])
    try:
        run_command(cmd)
    except KeyboardInterrupt:
        print("\n[INFO] Stopped MCP Inspector.")


def run_interactive_repl():
    """Interactive Python console to directly test domain services without MCP overhead."""
    print("\n" + "=" * 65)
    print(" Interactive Graph Intelligence Console (Direct Service Access)")
    print("=" * 65)
    print("Initializing services...")

    from graph_intelligence.reasoning.service import ReasoningService
    from graph_intelligence.memory.service import MemoryService
    from graph_intelligence.company_brain.service import CompanyBrainService
    from graph_intelligence.common.config import get_settings

    settings = get_settings()
    reasoning_svc = ReasoningService()
    memory_svc = MemoryService(user_id=settings.DEMO_USER_ID)
    brain_svc = CompanyBrainService()

    print(f"Connected to FalkorDB Graph: '{settings.FALKORDB_GRAPH}'")
    print(f"Active User: '{settings.DEMO_USER_ID}'")
    print("\nAvailable Commands:")
    print("  1. deps <service>          -> Find service dependencies (e.g. 'deps PaymentService')")
    print("  2. impact <service/ADR>    -> Analyze change blast radius (e.g. 'impact PaymentService')")
    print("  3. ask <question>          -> Source-backed Q&A (e.g. 'ask Who owns PaymentService?')")
    print("  4. search <query>          -> Search user memory (e.g. 'search retry')")
    print("  5. remember <text>         -> Save a quick memory summary")
    print("  6. status                  -> View memory status counts")
    print("  0. exit                    -> Return to main menu\n")

    while True:
        try:
            line = input("falkordb-console> ").strip()
            if not line:
                continue
            if line.lower() in ("exit", "quit", "0"):
                break

            parts = line.split(" ", 1)
            cmd = parts[0].lower()
            arg = parts[1].strip() if len(parts) > 1 else ""

            if cmd == "deps":
                if not arg:
                    print("Usage: deps <ServiceName> (e.g. deps PaymentService)")
                    continue
                res = reasoning_svc.find_service_dependencies(arg)
                _print_json(res)

            elif cmd == "impact":
                if not arg:
                    print("Usage: impact <ServiceName|ADR> (e.g. impact PaymentService)")
                    continue
                res = reasoning_svc.analyze_change_impact(arg)
                _print_json(res)

            elif cmd == "ask":
                if not arg:
                    print("Usage: ask <question> (e.g. ask Who owns PaymentService?)")
                    continue
                res = brain_svc.answer_company_question(arg)
                _print_json(res)

            elif cmd == "search":
                if not arg:
                    print("Usage: search <query> (e.g. search retry)")
                    continue
                res = memory_svc.search_user_memory(query=arg)
                _print_json(res)

            elif cmd == "remember":
                if not arg:
                    print("Usage: remember <summary text>")
                    continue
                res = memory_svc.remember_session_summary(
                    title="Console Quick Note",
                    summary=arg,
                    keywords=["console", "quicknote"],
                    entities=["PaymentService"],
                )
                _print_json(res)

            elif cmd == "status":
                res = memory_svc.get_memory_status()
                _print_json(res)

            else:
                print(f"Unknown command '{cmd}'. Try 'deps', 'impact', 'ask', 'search', 'remember', 'status', or 'exit'.")

        except KeyboardInterrupt:
            print("\n")
            break
        except Exception as e:
            print(f"[ERROR] {e}")


def _print_json(data):
    import json
    print(json.dumps(data, indent=2))


def print_menu():
    print("\n" + "=" * 65)
    print(" FalkorDB Graph Intelligence Platform Runner")
    print("=" * 65)
    print(" 1) Launch Reasoning MCP Server     (Interactive Web Inspector)")
    print(" 2) Launch Memory MCP Server        (Interactive Web Inspector)")
    print(" 3) Launch Corporate Brain MCP      (Interactive Web Inspector)")
    print(" 4) Interactive Terminal Console    (Direct Python REPL / No browser)")
    print(" 5) Run Automated Test Suite        (Equivalent to 'dotnet test')")
    print(" 6) Check Database Connection       (Ping FalkorDB & verify graph)")
    print(" 7) Clean & Re-seed Demo Database   (Reset graph to baseline)")
    print(" 0) Exit")
    print("=" * 65)


def main():
    parser = argparse.ArgumentParser(description="FalkorDB Graph Intelligence Runner (like 'dotnet run')")
    parser.add_argument("--server", choices=["reasoning", "memory", "brain"], help="Launch specified MCP server in Inspector")
    parser.add_argument("--repl", action="store_true", help="Launch interactive direct-service REPL")
    parser.add_argument("--test", action="store_true", help="Run full pytest test suite (like 'dotnet test')")
    parser.add_argument("--check", action="store_true", help="Check database connection")
    parser.add_argument("--seed", action="store_true", help="Clean and re-seed demo data")
    args = parser.parse_args()

    if args.server == "reasoning":
        launch_inspector("graph_intelligence.reasoning.mcp_server")
        return
    elif args.server == "memory":
        launch_inspector("graph_intelligence.memory.mcp_server", extra_env={"DEMO_USER_ID": "demo-user-dev"})
        return
    elif args.server == "brain":
        launch_inspector("graph_intelligence.company_brain.mcp_server")
        return
    elif args.repl:
        run_interactive_repl()
        return
    elif args.test:
        run_command([PYTHON_EXEC, "-m", "pytest", "tests", "-v"])
        return
    elif args.check:
        run_command([PYTHON_EXEC, "scripts/check_connection.py"])
        return
    elif args.seed:
        run_command([PYTHON_EXEC, "scripts/reset_demo.py", "--yes"])
        run_command([PYTHON_EXEC, "scripts/seed_demo.py"])
        run_command([PYTHON_EXEC, "scripts/verify_seed.py"])
        return

    # If no flags passed, show interactive menu
    while True:
        print_menu()
        choice = input("Select an option (0-7): ").strip()
        if choice == "1":
            launch_inspector("graph_intelligence.reasoning.mcp_server")
        elif choice == "2":
            launch_inspector("graph_intelligence.memory.mcp_server", extra_env={"DEMO_USER_ID": "demo-user-dev"})
        elif choice == "3":
            launch_inspector("graph_intelligence.company_brain.mcp_server")
        elif choice == "4":
            run_interactive_repl()
        elif choice == "5":
            run_command([PYTHON_EXEC, "-m", "pytest", "tests", "-v"])
        elif choice == "6":
            run_command([PYTHON_EXEC, "scripts/check_connection.py"])
        elif choice == "7":
            run_command([PYTHON_EXEC, "scripts/reset_demo.py", "--yes"])
            run_command([PYTHON_EXEC, "scripts/seed_demo.py"])
            run_command([PYTHON_EXEC, "scripts/verify_seed.py"])
        elif choice in ("0", "exit", "quit"):
            print("Exiting.")
            break
        else:
            print("Invalid option. Please enter 0-7.")


if __name__ == "__main__":
    main()
