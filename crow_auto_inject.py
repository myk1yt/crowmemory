#!/usr/bin/env python3
"""
crow_auto_inject.py — Auto-inject Crow memories into the LLM context.

This script is designed to run BEFORE every conversation/task.
It queries Crow for relevant memories and outputs them as a
[User Bias] block that should be prepended to the system prompt.

Usage:
    python crow_auto_inject.py "Fix the memory leak in PDF worker"
    python crow_auto_inject.py --domain code "Write TypeScript parser"
    python crow_auto_inject.py --all "What should I work on today?"

Integration:
    In Zoo Code, configure this as a pre-task hook so Crow memories
    are always injected before the LLM sees your query.
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from crow_core import CrowMemory, DOMAINS

DEFAULT_QUERY = "General coding and personal context"


def inject(query: str, domain: str = "all", state_path: str = "./memory/crow.bin"):
    """Generate the [User Bias] block for prompt injection."""
    crow = CrowMemory(state_path)

    # Determine which registers to query
    if domain == "all":
        registers = None  # All registers
    elif domain in DOMAINS:
        registers = DOMAINS[domain]
    else:
        registers = [domain]  # Single register

    # Get the bias block
    bias_block = crow.get_user_bias_block(query, registers)

    # Also get evolved permanent rules from system_prompt.md
    evolved_rules = ""
    prompt = crow.get_system_prompt()
    for line in prompt.split("\n"):
        if line.startswith("RULE:"):
            evolved_rules += f"- {line}\n"

    # Build the complete injection
    parts = []
    if evolved_rules.strip():
        parts.append("[Permanent Rules — evolved by Crow]")
        parts.append(evolved_rules.strip())
        parts.append("")

    parts.append(bias_block)

    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser(
        description="Crow Memory Auto-Inject — Generate [User Bias] block for LLM context"
    )
    parser.add_argument(
        "query", nargs="?", default=DEFAULT_QUERY,
        help="Current task description (default: general context)"
    )
    parser.add_argument(
        "--domain", "-d", default="all",
        choices=["code", "life", "all"] + list(DOMAINS.get("code", [])) + list(DOMAINS.get("life", [])),
        help="Domain to query (code/life/all, or specific register)"
    )
    parser.add_argument(
        "--state", default="./memory/crow.bin",
        help="Path to crow.bin"
    )
    parser.add_argument(
        "--evolve-only", action="store_true",
        help="Only output evolved permanent rules (no recall)"
    )
    args = parser.parse_args()

    if args.evolve_only:
        crow = CrowMemory(args.state)
        print(crow.get_system_prompt())
    else:
        block = inject(args.query, args.domain, args.state)
        print(block)


if __name__ == "__main__":
    main()
