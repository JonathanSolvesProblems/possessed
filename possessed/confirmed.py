"""Apply only the fixes a second check agrees with, for a PR to someone else's repository.

A fix is confirmed when the blind second judge gave the same verdict as Gemma 4, or a
hand label (labels.json) checked against the live page and the archive says so.

    uv run python -m possessed.confirmed path/to/clone [labels.json]
"""
import json
import sys
from pathlib import Path

from .repo import apply, markdown_files, report
from .links import extract


def main(root, labels_path=None):
    root = Path(root)
    results = json.loads((root / "possessed.json").read_text(encoding="utf-8"))
    second = {d["url"]: d["qwen"] for d in json.loads((root / "second_opinion.json").read_text(encoding="utf-8"))}
    hand = json.loads(Path(labels_path).read_text(encoding="utf-8")) if labels_path else {}
    keep = []
    for r in results:
        g = r["verdict"].get("verdict")
        label = hand.get(r["url"], {}).get("label") or (g if second.get(r["url"]) == g else None)
        if label == g and g in ("possessed", "moved", "dead"):
            keep.append(r)
    found = [{**l, "file": f.relative_to(root).as_posix()} for f in markdown_files(root)
             for l in extract(f.read_text(encoding="utf-8", errors="replace"))]
    fixes = apply(root, found, keep)
    body = report(keep, fixes, checked=len(results)) + ("\n\nEvery row was checked twice: by Gemma 4 and by a second model "
                                  "(Qwen 3.5 4B) that never saw Gemma's answer, with any disagreement checked by hand.")
    (root / "possessed-report.md").write_text(body, encoding="utf-8")
    print(f"{len(keep)} confirmed, {len(fixes)} replaced in the markdown; PR body in possessed-report.md")


if __name__ == "__main__":
    main(*sys.argv[1:3])
