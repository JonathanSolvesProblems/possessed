"""Outbound links in markdown, each with the sentence that cites it."""
import re
from urllib.parse import urlparse

LINK = re.compile(r"(?<!!)\[([^\]]{1,300})\]\((https?://[^)\s]+)\)")
SKIP_HOSTS = ("dev.to", "forem.com", "amazonaws.com", "cloudinary.com", "imgur.com", "giphy.com",
              "githubusercontent.com", "shields.io", "web.archive.org", "archive.org")


def cited_sentence(text, start, end):
    """The sentence (or list item) around a link, with markdown links reduced to their text."""
    lo = max(text.rfind("\n", 0, start), text.rfind(". ", 0, start)) + 1
    hi_candidates = [i for i in (text.find("\n", end), text.find(". ", end)) if i != -1]
    hi = min(hi_candidates) if hi_candidates else len(text)
    s = text[lo:hi + 1]
    s = LINK.sub(lambda m: m.group(1), s)
    return re.sub(r"[*_`#>]+", "", s).strip()[:400]


def extract(markdown):
    out, seen = [], set()
    for m in LINK.finditer(markdown):
        anchor, url = m.group(1).strip(), m.group(2).rstrip(".,;")
        host = urlparse(url).netloc.lower()
        if any(host == h or host.endswith("." + h) for h in SKIP_HOSTS) or url in seen:
            continue
        if re.search(r"\.(png|jpe?g|gif|svg|webp|mp4|pdf)(\?|$)", url, re.I):
            continue
        seen.add(url)
        out.append({"url": url, "anchor": anchor, "sentence": cited_sentence(markdown, m.start(), m.end())})
    return out
