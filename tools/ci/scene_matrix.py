#!/usr/bin/env python3
"""Print the render matrix of a run for GitHub Actions, one entry per scene of video/plan.json; exit 1 on a bad plan.

  python3 tools/ci/scene_matrix.py runs/<run>      # -> [{"id": "01", "file": "hilltop.py", "class": "Hilltop"}, ...]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "video"))
from _common import resolve_run  # noqa: E402
import plan as P  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    run = resolve_run(sys.argv[1])
    issues = P.problems(run)
    if issues:
        print("\n".join(f"error: {i}" for i in issues), file=sys.stderr)
        return 1
    scenes = P.load(run)["scenes"]
    print(json.dumps([{"id": f"{i:02d}", "file": s["file"], "class": s["class"]} for i, s in enumerate(scenes, 1)],
                     separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
