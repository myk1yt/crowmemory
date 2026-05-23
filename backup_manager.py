#!/usr/bin/env python3
"""
backup_manager.py — CLI utility for Crow Memory backup management.

Usage:
    python backup_manager.py create  --state ./memory/crow.bin --tag daily
    python backup_manager.py rotate  --state ./memory/crow.bin --max-daily 7
    python backup_manager.py list    --state ./memory/crow.bin
    python backup_manager.py recover --state ./memory/crow.bin
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from crow_core import CrowMemory


def cmd_create(args):
    crow = CrowMemory(args.state)
    path = crow.create_backup(tag=args.tag)
    print(f"Backup created: {path}")


def cmd_rotate(args):
    crow = CrowMemory(args.state)
    result = crow.rotate_backups(max_daily=args.max_daily,
                                 max_weekly=args.max_weekly)
    print(f"Rotated {result['rotated']} backups")
    for f in result["removed"]:
        print(f"  Removed: {f}")


def cmd_list(args):
    crow = CrowMemory(args.state)
    backups = crow.list_backups()
    if backups:
        print(f"Backups ({len(backups)}):")
        for b in backups:
            size = os.path.getsize(b) if os.path.exists(b) else 0
            print(f"  {b} ({size / 1024 / 1024:.1f} MB)")
    else:
        print("No backups found.")


def cmd_recover(args):
    crow = CrowMemory(args.state)
    result = crow.recover_from_drift()
    print(f"Action: {result['action']}")
    print(f"Message: {result['message']}")
    if "steps" in result:
        for step in result["steps"]:
            print(f"  Step: {step}")


def main():
    parser = argparse.ArgumentParser(description="Crow Memory Backup Manager")
    parser.add_argument("--state", default="./memory/crow.bin",
                        help="Path to crow.bin state file")
    sub = parser.add_subparsers(dest="command", required=True)

    p_create = sub.add_parser("create", help="Create a timestamped backup")
    p_create.add_argument("--tag", default="daily",
                          choices=["daily", "weekly", "manual"])

    p_rotate = sub.add_parser("rotate", help="Rotate old backups")
    p_rotate.add_argument("--max-daily", type=int, default=7)
    p_rotate.add_argument("--max-weekly", type=int, default=4)

    sub.add_parser("list", help="List all backups")

    sub.add_parser("recover", help="Attempt drift auto-recovery")

    args = parser.parse_args()

    commands = {
        "create": cmd_create,
        "rotate": cmd_rotate,
        "list": cmd_list,
        "recover": cmd_recover,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
