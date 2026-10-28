"""Score four detectors on the same links against reconciled labels.

Labels: where Gemma 4 and the blind Qwen 3.5 4B judge agree, that is the label. Where
they disagree, a hand label from labels.json (url -> {"label", "note"}), checked against
the live page and the archive, decides; without one the link is reported as unresolved
and left out of the scores, never silently counted.

Detectors, each asked "does this link need fixing?" (possessed, moved or dead):
  1. status-code link checker: passes every link in this set by construction
  2. URL heuristics: redirect to another domain, deep link to homepage, parking/gambling words
  3. EmbeddingGemma: cited sentence vs live page similarity below the run's 15th percentile
  4. Possessed: Gemma 4's verdict

    uv run python -m possessed.eval path/to/possessed.json [labels.json]
"""
import json
import sys
from pathlib import Path

FIX = {"possessed", "moved", "dead"}


def prf(pred, truth):
    tp = sum(p and t for p, t in zip(pred, truth))
    fp = sum(p and not t for p, t in zip(pred, truth))
    fn = sum(t and not p for p, t in zip(pred, truth))
    return {"flagged": tp + fp, "correct": tp, "false_alarms": fp, "missed": fn,
            "precision": round(tp / (tp + fp), 3) if tp + fp else None,
            "recall": round(tp / (tp + fn), 3) if tp + fn else None}


def main(path, labels_path=None):
    path = Path(path)
    results = json.loads(path.read_text(encoding="utf-8"))
    second = {d["url"]: d for d in json.loads(path.with_name("second_opinion.json").read_text(encoding="utf-8"))}
    hand = json.loads(Path(labels_path).read_text(encoding="utf-8")) if labels_path else {}
    sims = sorted(r["similarity"] for r in results)
    low = sims[int(len(sims) * 0.15)] if sims else 0

    rows, unresolved = [], []
    for r in results:
        g = r["verdict"].get("verdict")
        q = second.get(r["url"], {}).get("qwen")
        label = hand.get(r["url"], {}).get("label") or (g if g == q else None)
        if label is None:
            unresolved.append({"url": r["url"], "gemma": g, "qwen": q})
            continue
        rows.append((r, g, label))

    truth = [lab in FIX for _, _, lab in rows]
    truth_possessed = [lab == "possessed" for _, _, lab in rows]
    detectors = {
        "status-code link checker": [False] * len(rows),
        "URL heuristics (other domain, homepage, parking words)": [r["signals"]["moved_away"] or r["signals"]["to_homepage"] or r["signals"]["parked_words"] for r, _, _ in rows],
        "EmbeddingGemma similarity": [r.get("low_similarity", r["similarity"] <= low) for r, _, _ in rows],
        "Possessed (Gemma 4)": [g in FIX for _, g, _ in rows],
    }
    out = {
        "source": str(path), "judged": len(results), "scored": len(rows), "unresolved": unresolved,
        "agreement_gemma_qwen": round(sum(r["verdict"].get("verdict") == second.get(r["url"], {}).get("qwen") for r in results) / max(len(results), 1), 3),
        "labels": {k: sum(lab == k for _, _, lab in rows) for k in ("fine", "moved", "possessed", "dead")},
        "needs_fixing": {name: prf(p, truth) for name, p in detectors.items()},
        "possessed_only": {"Possessed (Gemma 4)": prf([g == "possessed" for _, g, _ in rows], truth_possessed),
                           "URL heuristics": prf(detectors["URL heuristics (other domain, homepage, parking words)"], truth_possessed)},
        "possessed_links": [{"url": r["url"], "now": r["live_final_url"], "title": r["live_title"]} for r, _, lab in rows if lab == "possessed"],
    }
    print(json.dumps({k: v for k, v in out.items() if k != "possessed_links"}, indent=1))
    Path("results").mkdir(exist_ok=True)
    name = path.parent.name
    Path(f"results/eval_{name}.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"-> results/eval_{name}.json")


if __name__ == "__main__":
    main(*sys.argv[1:3])
