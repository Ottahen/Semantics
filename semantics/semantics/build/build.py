#!/usr/bin/env python3
"""Build a standalone `ctf` binary with Nuitka.

    python build/build.py                # build for the current platform
    python build/build.py --onefile      # single-file binary (slower startup, easier to ship)

This compiles the Pro build (TUI + browser + MCP included). For a
core-only binary, drop `src/pro` from the --include-data-dir list and
skip `pip install -e ".[pro]"` before building.

Not run as part of this repo's automated tests — a full Nuitka compile
of Textual + Aider's dependency tree easily takes 10-20+ minutes and a
few GB of scratch space, which is a CI/release-pipeline job (see
.github/workflows/build.yml in the design doc), not a dev-loop one.
"""

from __future__ import annotations

import argparse
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENTRY = ROOT / "src" / "cli" / "main.py"


def build(onefile: bool, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "nuitka",
        "--standalone",
        "--follow-imports",
        f"--output-dir={output_dir}",
        f"--output-filename=ctf-{platform.system().lower()}-{platform.machine()}",
        # aider ships non-python resources (prompts, model-settings.yml) that
        # Nuitka's import-follower won't pick up on its own:
        "--include-package-data=aider",
        "--include-data-dir=" + str(ROOT / "src" / "pro" / "tui") + "=pro/tui",
        str(ENTRY),
    ]
    if onefile:
        cmd.insert(3, "--onefile")

    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=ROOT)
    print(f"\nBuild complete -> {output_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--onefile", action="store_true", help="Produce a single-file binary instead of a standalone dir.")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    build(onefile=args.onefile, output_dir=args.output_dir)


if __name__ == "__main__":
    main()
