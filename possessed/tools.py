"""Tools Gemma 4 uses to judge one link, and the gate in front of every replacement.

Evidence: fetch_live, find_snapshot, list_snapshots, read_snapshot.
Verdicts (one per link): fine, moved, possessed, dead.

The gate is code. A verdict that proposes a replacement is refused unless the
replacement is something this session actually saw:
  - possessed / dead: an archive snapshot that read_snapshot opened with status 200
  - moved: a live URL that fetch_live opened, which the link checker would pass
So Possessed cannot hand a maintainer a link nobody looked at.
"""
from .web import archived, fetch, list_captures, nearest_snapshot

VERDICTS = ("fine", "moved", "possessed", "dead")


def error(category, message, retryable=False):
    return {"isError": True, "errorCategory": category, "isRetryable": retryable, "message": message}


def short(page, n=1500):
    return {
        "status": page.status, "checker_says": page.kind, "error": page.error,
        "redirect_chain": page.chain[-6:], "final_url": page.final_url,
        "title": page.title, "text_start": page.text[:n],
    }


class LinkTools:
    def __init__(self, link: dict, cited_on: str, live=None):
        self.link, self.cited_on = link, cited_on    # cited_on: YYYY-MM-DD the post was published
        self.seen_live = {}                          # url -> Page
        self.seen_snapshots = {}                     # snapshot url -> Page
        if live is not None:
            self.seen_live[link["url"]] = live
        self.verdict = None
        self.refusals = []

    # ---- evidence
    def fetch_live(self, url: str | None = None):
        url = url or self.link["url"]
        page = self.seen_live.get(url) or fetch(url)
        self.seen_live[url] = page
        if page.final_url:
            self.seen_live.setdefault(page.final_url, page)
        return short(page)

    def find_snapshot(self, url: str | None = None, near_date: str | None = None):
        url = url or self.link["url"]
        near = (near_date or self.cited_on).replace("-", "")[:8]
        snap = nearest_snapshot(url, near)
        if snap is None:
            return error("transient", "The Internet Archive did not answer.", retryable=True)
        if not snap:
            return {"found": False, "message": f"The Internet Archive has no successful capture of {url}."}
        ts, original = snap
        return {"found": True, "timestamp": ts, "captured_on": f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}",
                "snapshot_url": f"https://web.archive.org/web/{ts}/{original}"}

    def list_snapshots(self, url: str | None = None):
        caps = list_captures(url or self.link["url"])
        if caps is None:
            return error("transient", "The Internet Archive did not answer.", retryable=True)
        return {"captures": [{"timestamp": t, "captured_on": f"{t[:4]}-{t[4:6]}-{t[6:8]}", "status": s} for t, s in caps]}

    def read_snapshot(self, timestamp: str, url: str | None = None):
        url = url or self.link["url"]
        page = archived(str(timestamp), url)
        if page.error:
            return error("transient", page.error, retryable=True)
        self.seen_snapshots[page.url] = page
        return {"snapshot_url": page.url, **short(page)}

    # ---- verdicts
    def fine(self, reason: str):
        return self._decide("fine", reason=reason)

    def moved(self, new_url: str, reason: str):
        page = self.seen_live.get(new_url)
        if page is None:
            return self._refuse(f"moved: {new_url} was never opened with fetch_live in this session. Open it first.")
        if page.kind != "ok":
            return self._refuse(f"moved: {new_url} returned {page.status or page.error}; a link checker would not pass it.")
        return self._decide("moved", replacement=page.final_url or new_url, reason=reason)

    def possessed(self, now_shows: str, originally: str, reason: str, replacement: str | None = None):
        if not replacement:
            return self._decide("possessed", replacement=None, reason=reason, now_shows=now_shows, originally=originally)
        return self._archived_verdict("possessed", replacement, reason, now_shows=now_shows, originally=originally)

    def dead(self, reason: str, replacement: str | None = None):
        if not replacement:
            return self._decide("dead", replacement=None, reason=reason)
        return self._archived_verdict("dead", replacement, reason)

    def _archived_verdict(self, name, replacement, reason, **extra):
        page = self.seen_snapshots.get(replacement)
        if page is None:
            return self._refuse(f"{name}: {replacement} is not a snapshot you opened with read_snapshot. "
                                "Open the snapshot you want to link to, then try again. If the archive has no "
                                "capture (try the parent path too), give the verdict with no replacement.")
        if page.status != 200 or not page.text:
            return self._refuse(f"{name}: that snapshot returned {page.status} with no readable text.")
        if page.title.lower().startswith("index of") or len(page.text) < 200:
            return self._refuse(f"{name}: that snapshot is an empty listing ('{page.title}'), not the resource. "
                                "Try another capture, or give the verdict with no replacement.")
        return self._decide(name, replacement=replacement, reason=reason, **extra)

    def _refuse(self, message):
        self.refusals.append(message)
        return error("business", "Refused. " + message)

    def _decide(self, name, **fields):
        if self.verdict:
            return error("validation", f"A verdict was already given ({self.verdict['verdict']}). End your turn.")
        self.verdict = {"verdict": name, **fields}
        return {"ok": True, "verdict": name, "next": "Done with this link. End your turn."}

    def call(self, name, args):
        fn = getattr(self, name, None) if name in TOOL_NAMES else None
        if fn is None:
            return error("validation", f"Unknown tool {name}.")
        try:
            return fn(**(args or {}))
        except TypeError as e:
            return error("validation", f"Bad arguments for {name}: {e}")


def _fn(name, description, props=None, required=()):
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": props or {}, "required": list(required)}}}


S = {"type": "string"}
SCHEMAS = [
    _fn("fetch_live", "Open a URL the way a reader's browser would today: status, redirect chain, final URL, page "
        "title and the start of its text. With no url, opens the link being judged. Use it to see where the link "
        "lands now, and to open a candidate new home before calling moved. For what the page used to be, use "
        "find_snapshot and read_snapshot instead.",
        {"url": {**S, "description": "Optional. e.g. https://example.com/docs/guide"}}),
    _fn("find_snapshot", "Find the Internet Archive's capture of a URL closest to (on or before) a date. With no "
        "arguments, finds the capture of the judged link nearest the day the post was published, which is what the "
        "author linked to. Returns a timestamp to pass to read_snapshot.",
        {"url": {**S, "description": "Optional, defaults to the judged link."},
         "near_date": {**S, "description": "Optional YYYY-MM-DD, defaults to the post's publish date."}}),
    _fn("list_snapshots", "List up to 40 captures of the judged link over the years, to see when it changed. Use it "
        "when the capture nearest the publish date already looks wrong (a parked page, an error) and you need an "
        "earlier good one."),
    _fn("read_snapshot", "Open an archived capture and read its title and text. Required before using that "
        "snapshot as a replacement.",
        {"timestamp": {**S, "description": "14-digit Wayback timestamp from find_snapshot or list_snapshots, e.g. 20210314052233"},
         "url": {**S, "description": "Optional, defaults to the judged link."}}, ["timestamp"]),
    _fn("fine", "Verdict: the link still opens what the author cited (the same page, or the same thing at a "
        "harmless new address such as https, www, x.com for twitter.com, youtube.com for youtu.be). No change needed.",
        {"reason": S}, ["reason"]),
    _fn("moved", "Verdict: the same thing lives at a new address, and the old link no longer reaches it (or "
        "reaches only a homepage). Give the new address. It must be a URL you opened with fetch_live.",
        {"new_url": S, "reason": S}, ["new_url", "reason"]),
    _fn("possessed", "Verdict: the link still answers, but it now opens something other than what the author cited: "
        "a parked or for-sale domain, a gambling or spam site, an unrelated company, or a generic homepage after "
        "the product was shut down. Replace it with the archived original, a snapshot you opened with read_snapshot. "
        "If the archive has no capture of the link or its parent path, leave replacement empty.",
        {"replacement": {**S, "description": "Optional. The snapshot_url from read_snapshot."},
         "now_shows": {**S, "description": "What the link opens today, in a few words."},
         "originally": {**S, "description": "What it was, in a few words, from the snapshot or the cited sentence."},
         "reason": S}, ["now_shows", "originally", "reason"]),
    _fn("dead", "Verdict: the link no longer opens anything usable (not found, domain gone, error page). Give the "
        "archived original as replacement if one exists and you opened it with read_snapshot; otherwise leave "
        "replacement empty.",
        {"reason": S, "replacement": {**S, "description": "Optional snapshot_url from read_snapshot."}}, ["reason"]),
]
TOOL_NAMES = {s["function"]["name"] for s in SCHEMAS}
