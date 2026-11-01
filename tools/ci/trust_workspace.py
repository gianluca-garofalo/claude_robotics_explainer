#!/usr/bin/env python3
"""Mark the CI checkout as a trusted workspace for Claude Code (GitHub Actions only).

  python3 tools/ci/trust_workspace.py "$GITHUB_WORKSPACE"

Headless runs never show the trust dialog, so the project's subagent frontmatter hooks (the reviewers' write guard)
would not run. The Claude Code docs describe trusting a folder by hand: projects["<repository root>"]
.hasTrustDialogAccepted = true in ~/.claude.json. This merges that one key into the file without touching the rest.
"""
import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    root = str(Path(sys.argv[1]).resolve())
    cfg = Path.home() / ".claude.json"
    data = json.loads(cfg.read_text(encoding="utf-8")) if cfg.exists() else {}
    data.setdefault("projects", {}).setdefault(root, {})["hasTrustDialogAccepted"] = True
    cfg.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"trusted {root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
