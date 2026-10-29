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
    # the five awesome lists judged locally; the Action run and the DEV study have their own facts
    lists = [d for d in Path("results").iterdir() if d.is_dir() and (d / "possessed.json").exists()
             and not d.name.endswith("-action") and d.name != "dev-study"]
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
    dev = load("results/dev-study/possessed.json")
    dsec = {d["url"]: d["qwen"] for d in load("results/dev-study/second_opinion.json")}
    dhand = load("results/labels_dev-study.json")
    dsum = load("results/dev-study/summary.json")
    f["dev.posts"], f["dev.unique"] = dsum["posts"], dsum["unique_links"]
    f["dev.passing"] = dsum["readable_passing"]
    f["dev.candidates"], f["dev.controls"] = dsum["candidates"], dsum["controls"]
    f["dev.judged"] = len(dev)
    ctrl = [r for r in dev if r["control"]]
    f["dev.controls_fine"] = sum(r["verdict"].get("verdict") == "fine" for r in ctrl)
    flagged = [r for r in dev if r["verdict"].get("verdict") in ("possessed", "moved", "dead")]

    def dlabel(r):
        g = r["verdict"]["verdict"]
        return dhand.get(r["url"], {}).get("label") or (g if dsec.get(r["url"]) == g else None)

    poss = [r for r in flagged if dlabel(r) == "possessed"]
    f["dev.possessed"] = len(poss)
    f["dev.posts_hit"] = len({r["post_id"] for r in poss})
    f["dev.reach"] = sum({r["post_id"]: r["reactions"] or 0 for r in poss}.values())
    f["dev.unconfirmed"] = sum(1 for r in flagged if dlabel(r) is None)
    f["dev.corrected"] = sum(1 for u, v in dhand.items()
                             if not u.startswith("_") and v["label"] not in ("possessed", "moved", "dead"))
    act = load("results/design-resources-action/possessed.json")
    run = load("results/design-resources-action/run.json")
    asum = load("results/design-resources-action/summary.json")
    f["action.read"] = len(act)
    f["action.fixed"] = sum(1 for r in act if r["verdict"].get("replacement"))
    f["action.gambling"] = sum(1 for r in act if r["url"] in labels["_gambling"]["urls"] and r["verdict"].get("replacement"))
    f["action.model_minutes"] = round(sum(e["seconds"] for r in act for e in r["trace"]) / 60)
    mins = sorted(sum(e["seconds"] for e in r["trace"]) / 60 for r in act)
    median = mins[len(mins) // 2]
    f["action.minutes_per_link"] = "two to three" if 2 <= median < 3 else f"{median:.1f}"
    f["action.wall_minutes"] = run["wall_minutes"]
    f["action.links"] = asum["links"]
    av = load("results/labels_awesome-vue.json")
    f["vue.removed"] = sum(1 for v in av.values() if isinstance(v, dict) and v.get("label") == "possessed")
    return f


# Each claim: (document, regex with one group, fact key, how to render the fact as text)
def n(x):
    return f"{x:,}"


def pct(x):
    return f"{x:.2f}"


CLAIMS = [
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
    ("post/dev-post.md", r": (\w+) were a trailing slash", "gate.unopened", lambda x: {7: "seven", 10: "ten", 11: "eleven", 12: "twelve"}.get(x, str(x))),
    ("post/dev-post.md", r", (\w+) were JavaScript-rendered snapshots", "gate.empty", lambda x: {7: "seven", 10: "ten", 11: "eleven", 12: "twelve"}.get(x, str(x))),
    ("post/dev-post.md", r"GPU the same (\d+) links took \d+ minutes", "dr.read", str),
    ("post/dev-post.md", r"GPU the same \d+ links took (\d+) minutes", "dr.gpu_minutes", str),
    ("post/dev-post.md", r"the ([\d,]+) most-loved posts on DEV", "dev.posts", n),
    ("post/dev-post.md", r"pulled their ([\d,]+) unique links", "dev.unique", n),
    ("post/dev-post.md", r"passes ([\d,]+) of them as readable", "dev.passing", n),
    ("post/dev-post.md", r"[Tt]riage picked ([\d,]+) candidates", "dev.candidates", n),
    ("post/dev-post.md", r"plus (\d+) random controls", "dev.controls", str),
    ("post/dev-post.md", r"judged all ([\d,]+) of them", "dev.judged", n),
    ("post/dev-post.md", r"(\d+) of the \d+ controls were fine", "dev.controls_fine", str),
    ("post/dev-post.md", r"\d+ of the (\d+) controls were fine", "dev.controls", str),
    ("post/dev-post.md", r"confirms? it: (\d+) links in \d+ posts", "dev.possessed", str),
    ("post/dev-post.md", r"confirms? it: \d+ links in (\d+) posts", "dev.posts_hit", str),
    ("post/dev-post.md", r"carrying ([\d,]+) reactions between them", "dev.reach", n),
    ("post/dev-post.md", r"and the ([\d,]+) links Gemma flagged but Qwen did not confirm", "dev.unconfirmed", n),
    ("post/dev-post.md", r"on vuejs/awesome-vue: \[#4593\].*?\. (Six|\d+) entries\.", "vue.removed", lambda x: {6: "Six"}.get(x, str(x))),
    ("post/dev-post.md", r"pull/1\)\. (\w+) links, \w+ of them gambling sites", "action.fixed", lambda x: {7: "Seven"}.get(x, str(x))),
    ("post/dev-post.md", r"pull/1\)\. \w+ links, (\w+) of them gambling sites", "action.gambling", lambda x: {6: "six"}.get(x, str(x))),
    ("post/dev-post.md", r"reads on the CPU, ([\w ]+) minutes a link", "action.minutes_per_link", str),
    ("post/dev-post.md", r"took (\d+) minutes end to end on a", "action.wall_minutes", str),
    ("post/dev-post.md", r"end to end on a ([\d,]+)-link list", "action.links", n),
    ("post/dev-post.md", r"then (\d+) minutes of Gemma 4 reading", "action.model_minutes", str),
    ("post/dev-post.md", r"of Gemma 4 reading (\w+) links\. (?:\w+) of the", "action.read", lambda x: {8: "eight"}.get(x, str(x))),
    ("post/dev-post.md", r"\. (\w+) of the \w+ were gambling or for-sale pages", "action.fixed", lambda x: {7: "Seven"}.get(x, str(x))),
    ("README.md", r"on the CPU, ([\w ]+) minutes a link", "action.minutes_per_link", str),
    ("README.md", r"no GPU\. (\w+) links, (?:\w+) of them", "action.fixed", lambda x: {7: "Seven"}.get(x, str(x))),
    ("README.md", r"no GPU\. \w+ links, (\w+) of them", "action.gambling", lambda x: {6: "six"}.get(x, str(x))),
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
