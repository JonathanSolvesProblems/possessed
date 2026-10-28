"""DEV's most-loved posts, every outbound link in them, and what each link returns today.

    uv run python -m possessed.crawl_dev 1000

Writes data/dev/posts.jsonl (post metadata and links) and data/dev/checks.jsonl
(one live fetch per unique URL). Both are append-only and resume on re-run.
"""
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

from .links import extract
from .web import UA, fetch

OUT = Path("data/dev")
API = "https://dev.to/api"


def dev_get(path, **params):
    for i in range(6):
        r = requests.get(f"{API}/{path}", params=params, headers={"User-Agent": UA, "Accept": "application/vnd.forem.api-v1+json"}, timeout=30)
        if r.status_code == 429:
            time.sleep(10 * (i + 1))
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"DEV API kept rate-limiting {path}")


def load(path):
    return [json.loads(l) for l in path.open(encoding="utf-8")] if path.exists() else []


def crawl_posts(n):
    path = OUT / "posts.jsonl"
    done = {p["id"] for p in load(path)}
    top = []
    for page in range(1, n // 100 + 2):
        top += dev_get("articles", top=3650, per_page=100, page=page)
        if len(top) >= n:
            break
    top = top[:n]
    with path.open("a", encoding="utf-8") as f:
        for i, a in enumerate(top, 1):
            if a["id"] in done:
                continue
            full = dev_get(f"articles/{a['id']}")
            f.write(json.dumps({
                "id": a["id"], "title": a["title"], "url": a["url"], "published_at": a["published_at"],
                "reactions": a.get("public_reactions_count"), "comments": a.get("comments_count"),
                "author": a["user"]["username"], "links": extract(full.get("body_markdown") or ""),
            }) + "\n")
            if i % 50 == 0:
                print(f"  posts {i}/{len(top)}", flush=True)
            time.sleep(0.3)


def check_links():
    posts = load(OUT / "posts.jsonl")
    path = OUT / "checks.jsonl"
    done = {c["url"] for c in load(path)}
    todo = sorted({l["url"] for p in posts for l in p["links"]} - done)
    print(f"{len(todo)} links to check ({len(done)} already checked)", flush=True)
    with path.open("a", encoding="utf-8") as f, ThreadPoolExecutor(24) as ex:
        for i, page in enumerate(ex.map(lambda u: fetch(u, text_limit=3000), todo), 1):
            f.write(json.dumps(page.as_dict()) + "\n")
            if i % 200 == 0:
                f.flush()
                print(f"  checked {i}/{len(todo)}", flush=True)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    crawl_posts(int(sys.argv[1]) if len(sys.argv) > 1 else 1000)
    check_links()
