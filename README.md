# Possessed

Your link checker is green. Some of those links now open a casino.

A link checker asks one question: did the server answer? When a domain expires and gets
bought, or a product is shut down and its address redirected, the server still answers.
The link passes, and readers land on a slot site, a "buy this domain" page or another
company's homepage.

Possessed reads the page. It runs after your link checker, and for each link the checker
passed, Gemma 4 compares what the link opens today with the Internet Archive's capture from
when the link was added. Then it decides:

- **fine**: same thing, maybe at a harmless new address
- **moved**: the same thing lives somewhere else now, and it follows it there
- **possessed**: the address now serves something else, so it is replaced with the archived original
- **dead**: gone, replaced with the archived original if one exists

Then it opens one pull request with the fixes and a table of evidence.

**What it cannot do:** it never links to a page it did not open. Every replacement is either
an archive capture that Gemma 4 read, or a live page that a link checker would pass. Pages
behind a bot check or rendered only by JavaScript are left alone and counted, not judged.

## Use it

```yaml
# .github/workflows/possessed.yml
on:
  schedule: [{ cron: "0 6 * * 1" }]
  workflow_dispatch:
permissions:
  contents: write
  pull-requests: write
jobs:
  possessed:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }   # the date each link was added comes from git history
      - uses: JonathanSolvesProblems/possessed@main
```

Locally, with [Ollama](https://ollama.com) running `gemma4:e4b` and `embeddinggemma`:

```
uv run python -m possessed.repo path/to/repo --no-write   # judge only
uv run python -m possessed.repo path/to/repo              # judge and fix the markdown
```

## How it works

1. Every markdown link is fetched the way a browser would follow it (redirects, meta refresh).
2. Triage picks the links worth a model's time: redirected to another domain, a deep link that
   now lands on a homepage, parking or gambling words on the page, or EmbeddingGemma rating the
   page far from the sentence that cites it.
3. Gemma 4 (via Ollama, native function calling) chooses its own evidence: the live page, the
   archive capture nearest the day the link was added (`git log -S`), older captures when that
   one is already broken. Then it gives one verdict.
4. A code gate refuses any replacement Gemma 4 did not open in that session, and sends the
   refusal back to it.

Runs on open-weight models only, on your machine or the Action runner, with no API key.
