"""Used by scripted fake turns: record an answer in the newest unanswered decision file of a run.

    python answer_decision.py <run dir> <answer text>
"""

import re
import sys
from pathlib import Path


def main() -> int:
    run_dir, text = Path(sys.argv[1]), sys.argv[2]
    files = sorted(run_dir.glob("decision_*_v*.md"), key=lambda p: int(re.search(r"_v(\d+)\.md$", p.name).group(1)))
    pending = [p for p in files if re.search(r"^answered: false$", p.read_text(), re.M)]
    if not pending:
        print("no unanswered decision file", file=sys.stderr)
        return 1
    path = pending[-1]
    head, body = path.read_text().split("## Answer", 1)
    path.write_text(head.replace("answered: false", "answered: true") + f"## Answer\n\n{text}\n\n## Approved edits\n\nnone\n")
    print(f"answered {path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
