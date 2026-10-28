"""Fail when a number in the write-up no longer matches the result files.

Every headline figure in README.md and post/dev-post.md is computed here from results/
and then looked for, as text, in the documents. A figure that drifted, a placeholder left
behind, or a retired claim that came back fails the build.

    uv run python check_claims.py
"""
import json
import re
import sys
from pathlib import Path

DOCS = [Path("README.md"), Path("post/dev-post.md")]
FIX = {"possessed", "moved", "dead"}


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def _key(url):
    return url.replace("id_/", "/").rstrip("/")


def facts():
    f = {}
    ev = load("results/eval_design-resources.json")
    s = load("results/design-resources/summary.json")
    f["dr.links"] = s["links"]
    f["dr.passing"] = s["checker"]["ok"]
    f["dr.unreadable"] = s["unreadable"]
    f["dr.read"] = ev["judged"]
    f["dr.scored"] = ev["scored"]
    f["dr.agree"] = round(ev["agreement_gemma_qwen"] * ev["judged"])
    f["dr.possessed"] = ev["labels"]["possessed"]
    f["dr.moved"] = ev["labels"]["moved"]
    f["dr.dead"] = ev["labels"]["dead"]
    f["dr.needs_fix"] = f["dr.possessed"] + f["dr.moved"] + f["dr.dead"]
    for key, name in (("heur", "URL heuristics (other domain, homepage, parking words)"),
                      ("emb", "EmbeddingGemma similarity"), ("gemma", "Possessed (Gemma 4)")):
        d = ev["needs_fixing"][name]
        f[f"dr.{key}.flagged"], f[f"dr.{key}.correct"], f[f"dr.{key}.precision"] = d["flagged"], d["correct"], d["precision"]
    po = ev["possessed_only"]
    f["dr.gemma.possessed_flagged"], f["dr.gemma.possessed_correct"] = po["Possessed (Gemma 4)"]["flagged"], po["Possessed (Gemma 4)"]["correct"]
    f["dr.heur.possessed_flagged"], f["dr.heur.possessed_correct"] = po["URL heuristics"]["flagged"], po["URL heuristics"]["correct"]
    labels = load("results/labels_design-resources.json")
    f["dr.gambling"] = len(labels["_gambling"]["urls"])
    possessed_urls = {p["url"] for p in ev["possessed_links"]}
    assert set(labels["_gambling"]["urls"]) <= possessed_urls, "a gambling url is not among the labelled possessed links"
    lists = [d for d in Path("results").iterdir() if d.is_dir() and (d / "possessed.json").exists()]
    f["lists"] = len(lists)
    judged = [r for d in lists for r in load(d / "possessed.json")]
    f["judged.total"] = len(judged)
    f["gate.refusals"] = sum(len(r["refusals"]) for r in judged)
    unopened, empty, spelling_only = 0, 0, True
    for r in judged:
        opened = {_key(p) for e in r["trace"] for res in e["results"] for p in [res.get("snapshot_url")] if p}
        for m in r["refusals"]:
            if "not a snapshot you opened" in m:
                unopened += 1
                spelling_only &= _key(m.split(" is not a snapshot")[0].split(": ", 1)[1]) in opened
            elif "empty listing" in m or "no text and only a generic title" in m:
                empty += 1
    f["gate.unopened"], f["gate.empty"] = unopened, empty
    assert unopened + empty == f["gate.refusals"], "a refusal of a third kind appeared; the post's sentence about the gate is stale"
    assert spelling_only, "a refused replacement was NOT a spelling variant of an opened snapshot; the post's claim is false"
    dr = load("results/design-resources/possessed.json")
    f["dr.gpu_minutes"] = round(sum(e["seconds"] for r in dr for e in r["trace"]) / 60)
    av = load("results/labels_awesome-vue.json")
    f["vue.removed"] = sum(1 for v in av.values() if isinstance(v, dict) and v.get("label") == "possessed")
    return f


# Each claim: (document, regex with one group, fact key, how to render the fact as text)
def n(x):
    return f"{x:,}"


def pct(x):
    return f"{x:.2f}"


CLAIMS = [
    ("post/dev-post.md", r"out of ([\d,]+) links the checker passes", "dr.passing", n),
    ("post/dev-post.md", r"turned ([\d,]+) passing links into", "dr.passing", n),
    ("post/dev-post.md", r"passing links into ([\d,]+) reads", "dr.read", n),
    ("post/dev-post.md", r"same ([\d,]+) links from design-resources", "dr.scored", n),
    ("post/dev-post.md", r"^(Eight|\d+) entries on that list open gambling sites", "dr.gambling", lambda x: {8: "Eight"}.get(x, str(x))),
    ("post/dev-post.md", r"Another (\d+) open a domain-for-sale", "dr.possessed", lambda x: str(x - 8)),
    ("post/dev-post.md", r"\| URL heuristics \(other domain, homepage, parking words\) \| (\d+) \|", "dr.heur.flagged", str),
    ("post/dev-post.md", r"\| URL heuristics \(other domain, homepage, parking words\) \| \d+ \| (\d+) \|", "dr.heur.correct", str),
    ("post/dev-post.md", r"\| URL heuristics \(other domain, homepage, parking words\) \| \d+ \| \d+ \| ([\d.]+) \|", "dr.heur.precision", pct),
    ("post/dev-post.md", r"\| EmbeddingGemma similarity alone \| (\d+) \|", "dr.emb.flagged", str),
    ("post/dev-post.md", r"\| EmbeddingGemma similarity alone \| \d+ \| (\d+) \|", "dr.emb.correct", str),
    ("post/dev-post.md", r"\| EmbeddingGemma similarity alone \| \d+ \| \d+ \| ([\d.]+) \|", "dr.emb.precision", pct),
    ("post/dev-post.md", r"\| Gemma 4 reading the page \| (\d+) \|", "dr.gemma.flagged", str),
    ("post/dev-post.md", r"\| Gemma 4 reading the page \| \d+ \| (\d+) \|", "dr.gemma.correct", str),
    ("post/dev-post.md", r"\| Gemma 4 reading the page \| \d+ \| \d+ \| ([\d.]+) \|", "dr.gemma.precision", pct),
    ("post/dev-post.md", r"Gemma 4 was right on (\d+) of \d+\.", "dr.gemma.possessed_correct", str),
    ("post/dev-post.md", r"Gemma 4 was right on \d+ of (\d+)\.", "dr.gemma.possessed_flagged", str),
    ("post/dev-post.md", r"heuristics were right on (\d+) of \d+\.", "dr.heur.possessed_correct", str),
    ("post/dev-post.md", r"heuristics were right on \d+ of (\d+)\.", "dr.heur.possessed_flagged", str),
    ("post/dev-post.md", r"that was (\d+) of the [\d,]+ passing links", "dr.unreadable", str),
    ("post/dev-post.md", r"Across ([\d,]+) judgments on \w+ lists", "judged.total", n),
    ("post/dev-post.md", r"Across [\d,]+ judgments on (\w+) lists", "lists", lambda x: {4: "four", 5: "five", 6: "six"}.get(x, str(x))),
    ("post/dev-post.md", r"the gate fired (\d+) times, and all \d+ were my bugs", "gate.refusals", str),
    ("post/dev-post.md", r"the gate fired \d+ times, and all (\d+) were my bugs", "gate.refusals", str),
    ("post/dev-post.md", r": (\w+) were a trailing slash", "gate.unopened", lambda x: {10: "ten", 11: "eleven", 12: "twelve"}.get(x, str(x))),
    ("post/dev-post.md", r", (\w+) were JavaScript-rendered snapshots", "gate.empty", lambda x: {10: "ten", 11: "eleven", 12: "twelve"}.get(x, str(x))),
    ("post/dev-post.md", r"the same 194 links took (\d+) minutes", "dr.gpu_minutes", str),
    ("post/dev-post.md", r"on vuejs/awesome-vue: \[#4593\].*?\. (Six|\d+) entries\.", "vue.removed", lambda x: {6: "Six"}.get(x, str(x))),
]

RETIRED = [  # claims that must never come back
    ("recall", r"recall of 1\.0|100% recall|recall: 1"),
]


def main():
    f = facts()
    bad = 0
    texts = {d.as_posix(): d.read_text(encoding="utf-8") for d in DOCS if d.exists()}
    for doc, text in texts.items():
        for m in re.finditer(r"\[X[^\]]*\]", text):
            bad += 1
            print(f"PLACEHOLDER {doc}: {m.group(0)[:60]}")
        for name, rx in RETIRED:
            if re.search(rx, text, re.I):
                bad += 1
                print(f"RETIRED CLAIM {doc}: {name}")
    for doc, rx, key, render in CLAIMS:
        text = texts.get(doc, "")
        m = re.search(rx, text, re.M | re.S)
        want = render(f[key])
        if not m:
            bad += 1
            print(f"MISSING {doc}: /{rx}/ (expected {want} for {key})")
        elif m.group(1) != want:
            bad += 1
            print(f"DRIFT {doc}: says {m.group(1)!r}, results say {want!r} ({key})")
    print(f"{len(CLAIMS)} claims checked against {len(f)} facts; {bad} problem(s)")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
