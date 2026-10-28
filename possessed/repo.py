"""Run Possessed on a repository: find possessed links in its markdown and fix them in place.

    uv run python -m possessed.repo path/to/clone [--limit N]

For every link a status-code checker would pass, triage decides whether Gemma 4
should read it. The date each link was added comes from git history (`git log -S`),
so the archive is compared with what the page was when the maintainer linked it.
Fixes are written into the files; the evidence goes to possessed-report.md (the PR
body) and possessed.json (the state a later run starts from).
"""
import argparse
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

from .agent import judge
from .links import extract
from .triage import signals, similarity
from .web import fetch

LOW_SIM_QUANTILE = 0.15
SKIP_DIRS = {".git", "node_modules", ".github"}


def markdown_files(root):
    return [p for p in root.rglob("*.md") if not SKIP_DIRS & set(p.relative_to(root).parts)
            and p.name.lower() not in ("possessed-report.md",)]


def added_on(root, rel, url):
    """The date of the oldest commit whose diff added this URL to this file."""
    out = subprocess.run(["git", "-C", str(root), "log", "--reverse", "--format=%cs", "-S", url, "--", rel],
                         capture_output=True, text=True, encoding="utf-8").stdout.split()
    return out[0] if out else date.today().isoformat()


def scan(root, limit=None):
    root = Path(root)
    found = []
    for f in markdown_files(root):
        rel = f.relative_to(root).as_posix()
        for l in extract(f.read_text(encoding="utf-8", errors="replace")):
            found.append({**l, "file": rel})
    urls = sorted({l["url"] for l in found})
    print(f"{len(found)} links ({len(urls)} unique) in {len({l['file'] for l in found})} markdown files", flush=True)
    with ThreadPoolExecutor(24) as ex:
        pages = dict(zip(urls, ex.map(fetch, urls)))
    unique = {l["url"]: l for l in found}.values()
    ok = [l for l in unique if pages[l["url"]].kind == "ok"]
    unreadable = [l for l in ok if not pages[l["url"]].readable]
    if unreadable:
        print(f"{len(unreadable)} links pass the checker but show a bot check or an empty JavaScript page; "
              "Possessed cannot read them without a browser and leaves them alone", flush=True)
    ok = [l for l in ok if pages[l["url"]].readable]
    sims = similarity(ok, [pages[l["url"]].as_dict() for l in ok]) if ok else []
    cut = sorted(sims)[int(len(sims) * LOW_SIM_QUANTILE)] if len(sims) else 0
    cand = []
    for l, s in zip(ok, sims):
        sig = signals(pages[l["url"]].as_dict())
        if sig["moved_away"] or sig["to_homepage"] or sig["parked_words"] or s <= cut:
            cand.append((l, sig, float(s)))
    cand.sort(key=lambda x: (not x[1]["parked_words"], not x[1]["moved_away"], not x[1]["to_homepage"], x[2]))
    kinds = {}
    for p in pages.values():
        kinds[p.kind] = kinds.get(p.kind, 0) + 1
    read = len(cand) if limit is None else min(len(cand), limit)
    print(f"link checker view: {kinds}; Gemma 4 will read {read} of the {len(ok)} it passes", flush=True)
    summary = {"links": len(found), "unique": len(urls), "files": len({l["file"] for l in found}), "checker": kinds,
               "unreadable": len(unreadable), "readable": len(ok), "candidates": len(cand), "read": read,
               "scanned_on": date.today().isoformat()}

    results = []
    for l, sig, s in cand[:limit]:
        when = added_on(root, l["file"], l["url"])
        log = []
        v, tools = judge(l, when, f"{root.name}/{l['file']}", live=pages[l["url"]], log=log)
        results.append({"url": l["url"], "file": l["file"], "anchor": l["anchor"], "sentence": l["sentence"],
                        "added_on": when, "live_final_url": pages[l["url"]].final_url, "live_title": pages[l["url"]].title,
                        "signals": sig, "similarity": round(s, 4), "verdict": v, "refusals": tools.refusals, "trace": log})
        print(f"  {v.get('verdict', 'ERROR'):9s} {l['url'][:100]}", flush=True)
    return found, results, summary


def apply(root, found, results):
    """Rewrite each possessed or moved link to its verified replacement, in every file that cites it."""
    root = Path(root)
    fixes = {r["url"]: r["verdict"]["replacement"] for r in results
             if r["verdict"].get("verdict") in ("possessed", "moved", "dead") and r["verdict"].get("replacement")}
    for rel in sorted({l["file"] for l in found if l["url"] in fixes}):
        f = root / rel
        text = f.read_text(encoding="utf-8")
        for old, new in fixes.items():
            text = text.replace(f"]({old})", f"]({new})")
        f.write_text(text, encoding="utf-8")
    return fixes


def clip(s, n=60):
    return s if len(s) <= n else s[:n].rsplit(" ", 1)[0] + "..."


def report(results, fixes, checked=None, removed=False):
    flagged = [r for r in results if r["verdict"].get("verdict") in ("possessed", "moved", "dead")]
    checked = len(results) if checked is None else checked
    lines = ["## Possessed links", "",
             "These links still pass a status-code link checker, but they no longer open what was linked. "
             "Gemma 4 compared each live page with the Internet Archive's capture from when the link was added. "
             + ("This PR removes the entries; the archive link in each row shows what the entry used to be."
                if removed else "Every replacement below is a page it opened; nothing here is guessed."), "",
             "| Link | Added | Today it opens | It was | Fix |", "|---|---|---|---|---|"]
    for r in flagged:
        v = r["verdict"]
        now = v.get("now_shows") or r["live_title"] or r["live_final_url"] or ""
        was = v.get("originally") or r["anchor"]
        if removed:
            fix = f"removed ([archived original]({v['replacement']}))" if v.get("replacement") else "removed"
        elif v.get("replacement"):
            fix = f"[{v['verdict']}]({v['replacement']})"
        else:
            fix = f"{v['verdict']}, no archived copy: please review"
        lines.append(f"| `{r['url'][:70]}` in `{r['file']}` | {r['added_on']} | {clip(now)} | {clip(was)} | {fix} |")
    done = "removed" if removed else "fixed"
    lines += ["", f"Read {checked} suspicious links; {len(flagged)} need a change, {len(fixes)} {done} in this PR.",
              "Possessed runs Gemma 4 and EmbeddingGemma locally. It cannot tell you a page was right, only that it "
              "matches what the archive saw when the link was added."]
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--no-write", action="store_true", help="judge only, do not edit files")
    ap.add_argument("--out", help="folder for possessed.json and possessed-report.md (default: the repository)")
    a = ap.parse_args()
    found, results, summary = scan(a.path, a.limit)
    fixes = {} if a.no_write else apply(a.path, found, results)
    out = Path(a.out or a.path)
    out.mkdir(parents=True, exist_ok=True)
    (out / "possessed.json").write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    (out / "possessed-report.md").write_text(report(results, fixes), encoding="utf-8")
    print(f"{len(fixes)} links fixed; report in {out / 'possessed-report.md'}")
