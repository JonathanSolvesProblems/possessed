"""A blind second judge from another model family (Qwen 3.5 4B).

It never sees Gemma's verdict or trace. It gets the cited sentence, the live page and
the archive capture nearest the date the link was added, all fetched fresh, plus the
same rubric, and answers in a fixed JSON shape. Disagreements go to a hand check.

    uv run python -m possessed.second_opinion path/to/possessed.json [--sample N]
"""
import argparse
import json
import random
from pathlib import Path

import ollama

from .web import archived, fetch, nearest_snapshot

JUDGE = "qwen3.5:4b"
RUBRIC = """You check whether a link in an article still opens what the author meant. Answer with one verdict:
fine (same thing; harmless changes like https, www, twitter->x, a redesign, newer docs of the same thing),
moved (same thing at a new address, including an official successor or a rebrand after acquisition),
possessed (the link answers but opens something else: parked or for-sale domain, casino/betting/spam, unrelated
company or product, SEO article about the old name, a generic homepage or retirement notice after shutdown),
dead (not found, error, nothing usable). A login wall is fine.
Reply with JSON only: {"verdict": "...", "now_shows": "a few words", "why": "one sentence"}"""


def evidence(url, added_on):
    live = fetch(url, text_limit=1200)
    snap = nearest_snapshot(url, added_on.replace("-", ""))
    old = archived(*snap, text_limit=1200) if snap else None
    return {
        "link": url, "linked_on": added_on,
        "today": {"status": live.status, "error": live.error, "lands_on": live.final_url, "title": live.title, "text": live.text[:1200]},
        "archive_when_linked": None if not old or old.error else {"captured": snap[0][:8], "title": old.title, "text": old.text[:1200]},
    }


def second_opinion(record):
    ev = evidence(record["url"], record["added_on"])
    msg = {"cited_sentence": record.get("sentence", ""), "link_text": record.get("anchor", ""), **ev}
    res = ollama.chat(model=JUDGE, messages=[{"role": "system", "content": RUBRIC},
                                             {"role": "user", "content": json.dumps(msg, ensure_ascii=False)}],
                      format="json", options={"temperature": 0}, think=False)
    try:
        out = json.loads(res.message.content)
    except ValueError:
        out = {"verdict": None, "why": "unparseable: " + res.message.content[:200]}
    if out.get("verdict") not in ("fine", "moved", "possessed", "dead"):
        out["verdict"] = None
    return out, ev


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--sample", type=int, help="second-guess every flagged link, plus this many random others")
    a = ap.parse_args()
    path = Path(a.path)
    records = json.loads(path.read_text(encoding="utf-8"))
    if a.sample is not None:
        flagged = [r for r in records if r["verdict"].get("verdict") in ("possessed", "moved", "dead")]
        rest = [r for r in records if r["verdict"].get("verdict") == "fine"]
        records = flagged + random.Random(0).sample(rest, min(a.sample, len(rest)))
    out_path = path.with_name("second_opinion.json")
    done = {r["url"]: r for r in json.loads(out_path.read_text(encoding="utf-8"))} if out_path.exists() else {}
    for r in records:
        if r["url"] in done or "verdict" not in r["verdict"]:
            continue
        op, ev = second_opinion(r)
        done[r["url"]] = {"url": r["url"], "gemma": r["verdict"]["verdict"], "qwen": op.get("verdict"),
                          "qwen_now_shows": op.get("now_shows"), "qwen_why": op.get("why"), "evidence": ev}
        print(f"{r['verdict']['verdict']:9s} vs {str(op.get('verdict')):9s} {r['url'][:80]}", flush=True)
        out_path.write_text(json.dumps(list(done.values()), indent=1, ensure_ascii=False), encoding="utf-8")
    agree = sum(d["gemma"] == d["qwen"] for d in done.values())
    print(f"agreement {agree}/{len(done)}")
