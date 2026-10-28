"""The DEV study: which links in DEV's most-loved posts are possessed?

    uv run python -m possessed.study triage        # signals + similarity for every link a checker passes
    uv run python -m possessed.study judge [N]     # Gemma 4 judges the candidates and a random control sample

Every link a status-code checker would pass is a case. Each unique URL is judged once,
in the context of the most-loved post that cites it. Verdicts append to
data/dev/verdicts.jsonl with the full tool trace, and resume on re-run.
"""
import json
import random
import sys
from pathlib import Path

from .agent import judge
from .triage import signals, similarity
from .web import Page

DATA = Path("data/dev")
CONTROL = 150          # random links triage did NOT flag, judged anyway to measure what triage misses
LOW_SIM_QUANTILE = 0.2


def load(path):
    return [json.loads(l) for l in path.open(encoding="utf-8")] if path.exists() else []


def cases():
    posts = load(DATA / "posts.jsonl")
    checks = {c["url"]: c for c in load(DATA / "checks.jsonl")}
    best = {}
    for p in sorted(posts, key=lambda p: -(p["reactions"] or 0)):
        for l in p["links"]:
            if l["url"] in checks and l["url"] not in best:
                best[l["url"]] = {**l, "post_id": p["id"], "post_title": p["title"], "post_url": p["url"],
                                  "published": p["published_at"], "reactions": p["reactions"]}
    return best, checks


def triage():
    best, checks = cases()
    ok = [u for u in best if checks[u]["kind"] == "ok"]
    sims = similarity([best[u] for u in ok], [checks[u] for u in ok])
    cut = sorted(sims)[int(len(sims) * LOW_SIM_QUANTILE)]
    rows = []
    for u, s in zip(ok, sims):
        sig = signals(checks[u])
        rows.append({"url": u, **sig, "similarity": round(float(s), 4), "low_similarity": bool(s <= cut)})
    for r in rows:
        r["candidate"] = r["moved_away"] or r["to_homepage"] or r["parked_words"] or r["low_similarity"]
    rng = random.Random(0)
    rest = [r for r in rows if not r["candidate"]]
    for r in rng.sample(rest, min(CONTROL, len(rest))):
        r["control"] = True
    with (DATA / "triage.jsonl").open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    kinds = {}
    for c in checks.values():
        kinds[c["kind"]] = kinds.get(c["kind"], 0) + 1
    print(f"{len(best)} unique links: {kinds}")
    print(f"checker passes {len(ok)}; candidates {sum(r['candidate'] for r in rows)} "
          f"(moved_away {sum(r['moved_away'] for r in rows)}, to_homepage {sum(r['to_homepage'] for r in rows)}, "
          f"parked_words {sum(r['parked_words'] for r in rows)}, low_similarity {sum(r['low_similarity'] for r in rows)}); "
          f"control {sum(r.get('control', False) for r in rows)}")


def page_from(check):
    return Page(**{k: check.get(k) for k in ("url", "status", "final_url", "title", "text", "error")}, chain=check.get("chain") or [])


def judge_all(limit=None):
    best, checks = cases()
    rows = load(DATA / "triage.jsonl")
    todo = [r for r in rows if r["candidate"] or r.get("control")]
    # strongest signals first, so a partial run still covers the likeliest cases
    todo.sort(key=lambda r: (not r["parked_words"], not r["moved_away"], not r["to_homepage"], r["similarity"]))
    out = DATA / "verdicts.jsonl"
    done = {v["url"] for v in load(out)}
    todo = [r for r in todo if r["url"] not in done][:limit]
    print(f"{len(todo)} links to judge ({len(done)} done)", flush=True)
    with out.open("a", encoding="utf-8") as f:
        for i, r in enumerate(todo, 1):
            c = best[r["url"]]
            log = []
            try:
                v, tools = judge(c, c["published"], c["post_title"], live=page_from(checks[r["url"]]), log=log)
                refusals = tools.refusals
            except Exception as e:  # one bad page must not stop the study, and must not look like a verdict
                v, refusals = {"error": f"{type(e).__name__}: {e}"}, []
            f.write(json.dumps({"url": r["url"], "post_id": c["post_id"], "published": c["published"],
                                "control": r.get("control", False), "verdict": v, "refusals": refusals,
                                "seconds": round(sum(e["seconds"] for e in log), 1), "trace": log}, default=str) + "\n")
            f.flush()
            print(f"[{i}/{len(todo)}] {v.get('verdict', 'ERROR'):9s} {r['url'][:90]}", flush=True)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "triage"
    if cmd == "triage":
        triage()
    else:
        judge_all(int(sys.argv[2]) if len(sys.argv) > 2 else None)
