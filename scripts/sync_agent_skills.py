#!/usr/bin/env python3
from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / ".agents/skills"
DST = ROOT / ".claude/skills"

parser = argparse.ArgumentParser()
parser.add_argument("--check", action="store_true")
args = parser.parse_args()

if args.check:
    problems: list[str] = []
    src_files = {p.relative_to(SRC) for p in SRC.rglob("*") if p.is_file()}
    dst_files = {p.relative_to(DST) for p in DST.rglob("*") if p.is_file()}
    if src_files != dst_files:
        problems.append("skill file sets differ")
    for rel in sorted(src_files & dst_files):
        if not filecmp.cmp(SRC / rel, DST / rel, shallow=False):
            problems.append(f"content differs: {rel}")
    if problems:
        print("sync_agent_skills: FAIL")
        for p in problems:
            print(" -", p)
        sys.exit(1)
    print("sync_agent_skills: OK")
    sys.exit(0)

if DST.exists():
    shutil.rmtree(DST)
shutil.copytree(SRC, DST)
print("sync_agent_skills: mirrored .agents/skills -> .claude/skills")
