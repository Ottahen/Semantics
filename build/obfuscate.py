#!/usr/bin/env python3
"""Obfuscate the closed-source `src/pro` tree with PyArmor before packaging.

    python build/obfuscate.py

Only `src/pro` is obfuscated — `src/core` and `src/cli` are BSD 2-Clause
and ship as plain source/bytecode. This keeps the open-core promise
literal: anyone can read and audit the agent loop and tool
implementations; only the Pro TUI/browser/MCP/license internals are
protected.

Like build.py, this isn't part of the automated test/dev loop — it's a
release-pipeline step. Requires `pip install pyarmor`.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRO_SRC = ROOT / "src" / "pro"
OBFUSCATED_OUT = ROOT / "build" / "obfuscated" / "pro"


def main() -> None:
    if shutil.which("pyarmor") is None:
        print("pyarmor not found. Install with: pip install pyarmor", file=sys.stderr)
        sys.exit(1)

    OBFUSCATED_OUT.parent.mkdir(parents=True, exist_ok=True)
    if OBFUSCATED_OUT.exists():
        shutil.rmtree(OBFUSCATED_OUT)

    cmd = [
        "pyarmor",
        "gen",
        "--recursive",
        "--output",
        str(OBFUSCATED_OUT),
        str(PRO_SRC),
    ]
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=ROOT)

    # styles.tcss and license_public_key.pem aren't Python — PyArmor won't
    # touch them, so copy them across explicitly.
    for pattern in ("**/*.tcss", "**/*.pem"):
        for src_file in PRO_SRC.glob(pattern):
            rel = src_file.relative_to(PRO_SRC)
            dest = OBFUSCATED_OUT / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dest)

    print(f"\nObfuscated Pro build -> {OBFUSCATED_OUT}")
    print("Next: point build.py's --include-data-dir at this output instead of src/pro.")


if __name__ == "__main__":
    main()
