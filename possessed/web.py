"""The live web and the Internet Archive, with every failure kept as a fact.

`fetch` returns what a reader's browser would land on today: status, redirect chain,
final URL, title and visible text. `snapshots` and `archived` read the Wayback
Machine. A blocked page (403, 429, 999 from bot walls) is reported as blocked, never
as dead and never as an empty page.
"""
import re
import time
from dataclasses import asdict, dataclass, field
from urllib.parse import urlparse

import requests
import tldextract
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"
BLOCKED = {401, 403, 405, 406, 429, 451, 999}
# bot walls served with a 200, which would otherwise look like a page that changed
CHALLENGE = re.compile(r"^(client challenge|just a moment|attention required|verify you are human|human verification|"
                       r"access denied|are you a robot|security check|ddos-guard|please wait)", re.I)
MIN_TEXT = 200  # less visible text than this, with no real title, is a JavaScript shell we cannot read without a browser
GENERIC_TITLE = re.compile(r"^(vue app|react app|vite app|vite \+ [\w +]+|webpack app|storybook|app|untitled|home|document|"
                           r"chrome web store|sandbox - codesandbox|.*\bloading\b.*)$", re.I)
TIMEOUT = 20
_session = requests.Session()
_session.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})


def domain(url):
    e = tldextract.extract(url)
    return e.top_domain_under_public_suffix or e.domain


@dataclass
class Page:
    url: str
    status: int | None = None
    final_url: str | None = None
    chain: list = field(default_factory=list)
    title: str = ""
    text: str = ""
    error: str | None = None      # DNS, TLS, timeout, too many redirects

    @property
    def kind(self):
        """What a status-code link checker would say."""
        if self.error:
            return "unreachable"
        if self.status in BLOCKED:
            return "blocked"
        if self.status and self.status >= 400:
            return "dead"
        return "ok"

    @property
    def readable(self):
        """Whether there is a page to judge: not a bot wall, not an empty JavaScript shell."""
        title = self.title.strip()
        shell = len(self.text) < MIN_TEXT and (not title or GENERIC_TITLE.match(title))
        return self.kind == "ok" and not CHALLENGE.match(title) and not shell

    @property
    def changed_domain(self):
        return bool(self.final_url) and domain(self.final_url) != domain(self.url)

    def as_dict(self):
        d = asdict(self)
        d["kind"], d["changed_domain"], d["readable"] = self.kind, self.changed_domain, self.readable
        return d


def visible_text(html, limit=6000):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "template"]):
        tag.decompose()
    title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""
    text = re.sub(r"\s+", " ", soup.get_text(" ")).strip()
    return title[:300], text[:limit]


def fetch(url, text_limit=6000):
    p = Page(url=url)
    try:
        r = _session.get(url, timeout=TIMEOUT, allow_redirects=True)
        p.status, p.final_url = r.status_code, r.url
        p.chain = [h.url for h in r.history] + [r.url]
        if "html" in r.headers.get("Content-Type", "") or r.text.lstrip()[:15].lower().startswith(("<!doctype", "<html")):
            # bytes, so BeautifulSoup reads the page's own charset instead of requests' ISO-8859-1 default
            p.title, p.text = visible_text(r.content, text_limit)
        # client-side redirects that requests cannot follow
        m = re.search(r'http-equiv=["\']?refresh["\']?[^>]*url=([^"\'>\s]+)', r.text[:5000], re.I) or \
            re.search(r'window\.location(?:\.href)?\s*=\s*["\']([^"\']+)["\']', r.text[:5000])
        if m and m.group(1).startswith("http") and domain(m.group(1)) != domain(p.final_url):
            p.chain.append(m.group(1))
            p.final_url = m.group(1)
    except requests.TooManyRedirects:
        p.error = "too many redirects"
    except requests.exceptions.SSLError:
        p.error = "TLS error"
    except requests.exceptions.ConnectionError as e:
        p.error = "DNS failure" if "NameResolution" in str(e) or "getaddrinfo" in str(e) else "connection failed"
    except requests.exceptions.Timeout:
        p.error = "timeout"
    except Exception as e:
        p.error = type(e).__name__
    return p


# ---- Wayback Machine

CDX = "https://web.archive.org/cdx/search/cdx"


def _wayback_get(url, params=None, tries=4):
    for i in range(tries):
        try:
            r = _session.get(url, params=params, timeout=40)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(5 * (i + 1))
                continue
            return r
        except requests.RequestException:
            time.sleep(5 * (i + 1))
    return None


def snapshots(url, before=None, after=None, limit=12):
    """Successful (200) captures of `url`, as [(timestamp, original)], oldest first.
    Returns None when the archive could not be reached, [] when it has none."""
    params = {"url": url, "output": "json", "filter": "statuscode:200", "collapse": "timestamp:6", "limit": str(limit)}
    if before:
        params["to"] = before
    if after:
        params["from"] = after
    r = _wayback_get(CDX, params)
    if r is None or r.status_code != 200:
        return None
    try:
        rows = r.json()
    except ValueError:
        return None
    return [(row[1], row[2]) for row in rows[1:]]


def list_captures(url, limit=40):
    """[(timestamp, status)] spread over the years (one per quarter), or None if the archive did not answer."""
    params = {"url": url, "output": "json", "collapse": "timestamp:6", "fl": "timestamp,statuscode", "limit": "400"}
    r = _wayback_get(CDX, params)
    if r is None or r.status_code != 200:
        return None
    try:
        rows = [tuple(x) for x in r.json()[1:]]
    except ValueError:
        return None
    step = max(1, len(rows) // limit)
    return rows[::step][:limit]


def nearest_snapshot(url, yyyymmdd):
    """The last good capture on or before a date, else the first one after it."""
    before = snapshots(url, before=yyyymmdd, limit=-6)  # negative limit: the last N
    if before is None:
        return None
    if before:
        return before[-1]
    after = snapshots(url, after=yyyymmdd, limit=1)
    return after[0] if after else ()


def archived(timestamp, url, text_limit=6000):
    """The archived page as it was, without the Wayback toolbar (id_ mode)."""
    snap = f"https://web.archive.org/web/{timestamp}id_/{url}"
    r = _wayback_get(snap)
    p = Page(url=f"https://web.archive.org/web/{timestamp}/{url}")
    if r is None:
        p.error = "archive unreachable"
        return p
    p.status, p.final_url = r.status_code, p.url
    p.title, p.text = visible_text(r.content, text_limit)
    return p


def same_page(a, b):
    """Harmless moves a reader would not notice: scheme, www, trailing slash, youtu.be, twitter.com -> x.com."""
    def norm(u):
        u = urlparse(u)
        host = u.netloc.lower().removeprefix("www.").replace("twitter.com", "x.com")
        return host, u.path.rstrip("/")
    return norm(a) == norm(b)
