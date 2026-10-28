"""Gemma 4 judges one link: fine, moved, possessed or dead, with a verified replacement.

Gemma chooses which evidence to pull (the live page, the archive's capture from the
publish date, older captures) and when it has seen enough. The loop runs until Gemma
ends its turn; a reply cut off by the length limit is an error, never a verdict.
"""
import json
import os
import time

import ollama

from .tools import SCHEMAS, LinkTools

MODEL = os.environ.get("POSSESSED_MODEL", "gemma4:e4b")
MAX_STEPS = 10  # safety net against a runaway loop, never the normal stop

SYSTEM = """You check one link in a published article: does it still open what the author meant?
You get the sentence that cites the link, the link text, and the date the article was published.

Verdicts:
- fine: it still opens the same thing. Harmless changes are fine: https, www, a trailing slash,
  twitter.com to x.com, youtu.be to youtube.com, a redesigned page with the same content, a newer version of the same docs.
- moved: the same thing now lives at a new address, and you opened that address. This includes an official
  successor: the project renamed itself, moved to its own domain, or was acquired and lives on under the new owner
  with the same purpose (a docs site that moved, a library's new home, an app rebranded after an acquisition).
- possessed: the link still answers but opens something the author did not mean: a parked or for-sale domain,
  a casino, betting or spam site, an unrelated company or product, an SEO article about the old name, or a
  generic homepage or "we're retiring this" notice after the thing was shut down. Replace it with the archived original.
- A sign-in wall (accounts.google.com, a login page) or a bot check ("Client Challenge", "Just a moment", captcha) is
  not possession: say fine with "blocked, cannot verify".
- The same product grown or redesigned under the same name (new version, new pricing, more features, an AI pivot by
  the same team) is fine. A page now saying the project is retired, closed or shutting down is possessed.
- dead: not found, gone, an error page. Replace it with the archived original if there is one.

How to work:
1. fetch_live first. If the page plainly matches the cited sentence, say fine. One call is enough.
2. If it doesn't match, or you can't tell, find_snapshot (defaults to the publish date) and read_snapshot, then compare.
   If that capture is itself already broken or parked, list_snapshots and read an earlier one.
   If the archive has no capture of the exact URL, try find_snapshot on its parent path (drop the last segment).
   If there is still none, give the verdict without a replacement.
3. A page that blocks robots (403, captcha) is not evidence of anything: judge from what you can see, or say fine
   with the reason "blocked, cannot verify" when there is nothing else to go on.
4. Give exactly one verdict, then end your turn. Never invent a URL: replacements come only from pages you opened.

Hard cases:
- Cited "free design resources at UI Space"; live page is an online casino; the 2021 capture is UI Space's resource library.
  -> possessed, replacement = that capture.
- Cited "InVision's design resources"; live redirects to miro.com's homepage; capture shows InVision's resource page.
  -> possessed (product shut down, link now lands on another company's homepage).
- Cited "the React docs on hooks"; live redirects from reactjs.org/docs/hooks-intro.html to react.dev/reference/react
  with hooks content. -> fine (same thing, official new home).
- Cited "my Twitter"; live is x.com/username. -> fine.
- Cited "particles.matteobruni.it, a particles library"; live redirects to particles.js.org, the tsParticles site by the
  same project. -> moved (the project's own new home).
- Cited "Bumbag, a React UI kit"; live is "bumbag.style, buy this expired domain". -> possessed.
"""


def judge(link, published, title, live=None, model=MODEL, log=None):
    """Returns (verdict dict or {"error": ...}, tools). `live` is an optional Page already fetched."""
    log = [] if log is None else log
    tools = LinkTools(link, published[:10], live=live)
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": json.dumps({
            "article": title, "published": published[:10], "link": link["url"],
            "link_text": link.get("anchor", ""), "cited_in": link.get("sentence", "")}, ensure_ascii=False)},
    ]
    for step in range(MAX_STEPS):
        t0 = time.time()
        res = ollama.chat(model=model, messages=messages, tools=SCHEMAS, options={"temperature": 0.1, "num_ctx": 16384})
        msg = res.message
        messages.append(msg)
        calls = msg.tool_calls or []
        entry = {"step": step, "seconds": round(time.time() - t0, 1), "text": (msg.content or "")[:500],
                 "calls": [{"name": c.function.name, "args": c.function.arguments} for c in calls], "results": []}
        log.append(entry)
        if calls:
            for c in calls:
                result = tools.call(c.function.name, c.function.arguments)
                entry["results"].append(result)
                messages.append({"role": "tool", "tool_name": c.function.name,
                                 "content": json.dumps(result, ensure_ascii=False, default=str)})
            continue
        if res.done_reason == "length":
            return {"error": "Gemma's reply was cut off by the length limit; no verdict."}, tools
        if tools.verdict:
            return tools.verdict, tools
        messages.append({"role": "user", "content": "You ended without a verdict. Call exactly one of fine, moved, possessed or dead."})
    return {"error": f"No verdict after {MAX_STEPS} steps."}, tools
