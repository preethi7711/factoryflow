"""PreToolUse hook: block Claude from editing protected files.

Claude Code sends the tool call as JSON on stdin. Exit code 2 blocks the call and
shows stderr to Claude; exit 0 lets it through.

Protected: docs/PROBLEM.md (the brief, kept verbatim) and every .env file
(.env, .env.local, .env.production, ...) except .env.example, which holds no secrets.
"""

import json
import sys
from pathlib import PurePath


def is_protected(path: str) -> bool:
    p = PurePath(path.replace("\\", "/"))
    name = p.name.lower()
    if name == ".env.example":
        return False
    if name == ".env" or name.startswith(".env."):
        return True
    parts = [part.lower() for part in p.parts]
    return parts[-2:] == ["docs", "problem.md"]


def main() -> int:
    data = json.load(sys.stdin)
    path = data.get("tool_input", {}).get("file_path", "")
    if path and is_protected(path):
        print(f"Blocked by project hook: {path} is protected. Ask the user to edit it.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
