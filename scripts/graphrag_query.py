#!/usr/bin/env python3
"""
GraphRAG query wrapper for Hermes.
Calls graphrag query from the venv and returns structured results.
Usage: python3 graphrag_query.py "Who is John Treleven?" [--mode local|global|drift|basic]
"""
import sys, subprocess, json, os
from pathlib import Path

VENV_BIN = str(Path.home() / ".hermes" / "venvs" / "graphrag" / "bin")
GRAPH_ROOT = str(Path.home() / ".hermes" / "graphrag")

def query_graphrag(question, mode="local"):
    """Run graphrag query and return results."""
    cmd = [
        os.path.join(VENV_BIN, "graphrag"), "query",
        "--root", GRAPH_ROOT,
        "--method", mode,
        question
    ]
    env = os.environ.copy()
    env["PATH"] = f"{VENV_BIN}:{env.get('PATH', '')}"
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, env=env)
    if result.returncode != 0:
        return {"error": result.stderr[:2000], "success": False}
    output = result.stdout.strip()
    if not output:
        return {"error": "Empty response from graphrag", "success": False}
    return {"answer": output, "success": True}

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: graphrag_query.py <question> [--mode local|global|drift|basic]")
        sys.exit(1)
    
    question = sys.argv[1]
    mode = "local"
    if "--mode" in sys.argv:
        idx = sys.argv.index("--mode")
        if idx + 1 < len(sys.argv):
            mode = sys.argv[idx + 1]
    
    result = query_graphrag(question, mode)
    if result["success"]:
        print(result["answer"])
    else:
        print(f"ERROR: {result['error']}")
        sys.exit(1)
