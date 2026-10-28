"""Cheap first pass: which links that a link checker passes should Gemma 4 read?

Signals, all computed without Gemma 4:
  - moved_away: redirects to a different registrable domain (not a harmless move like twitter -> x)
  - to_homepage: a deep link that now lands on a site root
  - parked_words: parking, for-sale or gambling words in the live title or opening text
  - similarity: EmbeddingGemma cosine between the cited sentence and the live page

A link is a candidate when any of the first three fire, or its similarity is in the
bottom quarter. Each signal alone is also scored as a baseline in eval.py.
"""
import re
from urllib.parse import urlparse

import numpy as np
import ollama

from .web import domain, same_page

PARKED = re.compile(
    r"\b(domain (is )?for sale|buy this domain|this domain may be for sale|parked (free|domain)|domain parking|"
    r"hugedomains|sedo|dan\.com|afternic|godaddy auction|casino|slot ?online|slot gacor|judi|togel|poker online|"
    r"betting|sportsbook|bandar|situs)\b", re.I)
EMBED = "embeddinggemma"


def signals(page):
    p0, p1 = urlparse(page["url"]), urlparse(page.get("final_url") or page["url"])
    moved_away = bool(page.get("final_url")) and domain(page["final_url"]) != domain(page["url"]) \
        and not same_page(page["url"], page["final_url"]) \
        and not (domain(page["url"]) in ("youtu.be", "twitter.com") and domain(page["final_url"]) in ("youtube.com", "x.com"))
    to_homepage = p0.path.strip("/") != "" and p1.path.strip("/") == "" and not p1.query
    parked = bool(PARKED.search(page.get("title", "") + " " + page.get("text", "")[:1500]))
    return {"moved_away": moved_away, "to_homepage": to_homepage, "parked_words": parked}


def embed(texts, batch=64):
    out = []
    for i in range(0, len(texts), batch):
        out += ollama.embed(model=EMBED, input=[t[:2000] or " " for t in texts[i:i + batch]]).embeddings
    v = np.array(out, dtype=float)
    return v / np.linalg.norm(v, axis=1, keepdims=True).clip(1e-9)


def similarity(cited, live_pages):
    a = embed([f"{c.get('anchor', '')}. {c.get('sentence', '')}" for c in cited])
    b = embed([f"{p.get('title', '')}. {p.get('text', '')[:1500]}" for p in live_pages])
    return (a * b).sum(axis=1)
