"""PostToolUse hook: format and lint every .py file Claude edits.

Runs `ruff format` then `ruff check --fix`. If problems remain that ruff can't fix,
exit 2 so Claude sees them and fixes the code. Skips quietly if ruff isn't installed.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path


def find_ruff(project: Path) -> list[str] | None:
    for venv_bin in ("Scripts/ruff.exe", "bin/ruff"):  # Windows, then Linux/macOS
        candidate = project / "backend" / ".venv" / venv_bin
        if candidate.exists():
            return [str(candidate)]
    found = shutil.which("ruff")
    return [found] if found else None


def main() -> int:
    data = json.load(sys.stdin)
    path = data.get("tool_input", {}).get("file_path", "")
    if not path.endswith(".py"):
        return 0
    project = Path(__file__).resolve().parents[2]
    ruff = find_ruff(project)
    if ruff is None:
        return 0
    # Run from backend/ so ruff picks up backend/pyproject.toml.
    cwd = project / "backend"
    subprocess.run([*ruff, "format", "--quiet", path], cwd=cwd, check=False)
    result = subprocess.run(
        [*ruff, "check", "--fix", "--quiet", path], cwd=cwd, capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"ruff found problems it could not fix:\n{result.stdout}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
