"""Local helper to permanently change a job's status in data/jobs.db.

The website's status dropdown only saves to the browser. Use this to persist a
change into the committed database.

Usage (from the project root):
    python -m scripts.set_status --list
    python -m scripts.set_status "https://job-url" "Applied"

Statuses are free-text but the website understands:
    Not Applied | Applied | Interviewing | Rejected | Saved
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running as a script from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import db  # noqa: E402


def main(argv: list[str]) -> None:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return

    if argv[0] == "--list":
        for j in db.get_all_jobs():
            print(f"[{j['status']:<12}] {j['score']:>2}  {j['title'][:45]:<45}  {j['url']}")
        return

    if len(argv) < 2:
        print("Need both a URL and a status. See --help.")
        return

    url, status = argv[0], argv[1]
    db.set_status(url, status)
    print(f"Set status of {url} -> {status}")


if __name__ == "__main__":
    main(sys.argv[1:])
