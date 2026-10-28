"""Apply only the fixes a second check agrees with, for a PR to someone else's repository.

A fix is confirmed when the blind second judge gave the same verdict as Gemma 4, or a
hand label (labels.json) checked against the live page and the archive says so.

    uv run python -m possessed.confirmed path/to/clone [--labels labels.json] [--only possessed] [--remove]

--remove deletes the list entry instead of pointing it at the archive, for lists whose
maintainers drop entries for things that no longer exist. The archive link still goes
in the PR body as the evidence.
"""
import argparse
import json
import re
from pathlib import Path

from .repo import apply, markdown_files, report
from .links import extract


def remove(root, found, results):
    """Delete each list line that links to a confirmed url, in every file that cites it."""
    urls = {r["url"] for r in results}
    for rel in sorted({l["file"] for l in found if l["url"] in urls}):
        f = root / rel
        lines = f.read_text(encoding="utf-8").splitlines(keepends=True)
        keep = [s for s in lines if not (re.match(r"\s*[-*] ", s) and any(f"]({u})" in s for u in urls))]
        f.write_text("".join(keep), encoding="utf-8")
    return {u: None for u in urls}


def main(root, labels_path=None, only=("possessed", "moved", "dead"), removing=False):
    root = Path(root)
    results = json.loads((root / "possessed.json").read_text(encoding="utf-8"))
    second = {d["url"]: d["qwen"] for d in json.loads((root / "second_opinion.json").read_text(encoding="utf-8"))}
    hand = json.loads(Path(labels_path).read_text(encoding="utf-8")) if labels_path else {}
    keep = []
    for r in results:
        g = r["verdict"].get("verdict")
        label = hand.get(r["url"], {}).get("label") or (g if second.get(r["url"]) == g else None)
        if label == g and g in only:
            keep.append(r)
    found = [{**l, "file": f.relative_to(root).as_posix()} for f in markdown_files(root)
             for l in extract(f.read_text(encoding="utf-8", errors="replace"))]
    fixes = remove(root, found, keep) if removing else apply(root, found, keep)
    body = report(keep, fixes, checked=len(results), removed=removing) + (
        "\n\nEvery row was checked twice: by Gemma 4 and by a second model (Qwen 3.5 4B) that never saw "
        "Gemma's answer, with any disagreement checked by hand.")
    (root / "possessed-report.md").write_text(body, encoding="utf-8")
    print(f"{len(keep)} confirmed, {len(fixes)} {'removed' if removing else 'replaced'} in the markdown; "
          "PR body in possessed-report.md")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--labels")
    ap.add_argument("--only", nargs="+", default=["possessed", "moved", "dead"])
    ap.add_argument("--remove", action="store_true", help="delete the entry; the archive link goes in the PR body")
    a = ap.parse_args()
    main(a.path, a.labels, tuple(a.only), a.remove)
