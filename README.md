# Possessed

Your link checker is green. Some of those links now open a casino.

A link checker asks one question: did the server answer? When a domain expires and someone
buys it, or a product shuts down and its address is pointed at the buyer's homepage, the
server still answers. The link passes, and readers land on a slot site, a "buy this domain"
page or a company that has nothing to do with the words next to the link.

Possessed reads the page. It runs after your link checker, and for each link the checker
passed, Gemma 4 compares what the link opens today with the Internet Archive's capture from
the day the link was added to your repository. Then it gives one verdict:

- **fine**: the same thing, maybe at a harmless new address (https, www, x.com for twitter.com)
- **moved**: the same thing lives somewhere else now, and the link is pointed there
- **possessed**: the address serves something else now, so the link is pointed at the archived original
- **dead**: gone, pointed at the archived original if one exists

It opens one pull request with the fixes and, for every row, what the page was and what it is now.

**What it cannot do:** it never links to a page it did not open. Every replacement is either an
archive capture Gemma 4 read in that session, or a live page a link checker would pass; a
verdict that proposes anything else is refused by code and sent back to the model. Pages behind a
bot check, and pages that are only JavaScript, are counted and left alone. And Possessed cannot
tell you a page is *right*, only that it still matches what the archive saw when you linked it.

Runs on open-weight models only, through [Ollama](https://ollama.com), with no API key: `gemma4:e4b`
judges, `embeddinggemma` triages, and `qwen3.5:4b` gives a blind second opinion when you ask for one.

## Use it as a GitHub Action

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
        with:
          limit: 40                # links Gemma 4 reads per run; strongest signals first
```

Your repository needs *Settings → Actions → General → Allow GitHub Actions to create and approve
pull requests* turned on, or the last step cannot open the PR.

On a hosted runner Gemma 4 runs on the CPU, at about three minutes a link, so `limit` keeps a run
inside an hour or two; the weekly schedule gets through a long list over a few weeks. A
self-hosted runner that already has Ollama and a GPU is used as is and reads a thousand-link list
in under half an hour. The models are cached between runs. The evidence (`possessed.json`, with
every tool call Gemma made, and the report) is kept as a workflow artifact and never committed to
your repository.

## Use it locally

With Ollama running and `gemma4:e4b` plus `embeddinggemma` pulled:

```
uv run python -m possessed.repo path/to/clone --no-write        # judge only; evidence in possessed.json
uv run python -m possessed.repo path/to/clone                   # judge and rewrite the markdown
uv run python -m possessed.repo path/to/clone --limit 20 --out ./out
```

For a pull request to someone else's repository, get a second opinion first and apply only what
both models agree on (or what you confirmed by hand):

```
uv run python -m possessed.second_opinion path/to/clone/possessed.json      # qwen3.5:4b, never shown Gemma's answer
uv run python -m possessed.confirmed path/to/clone --labels my_labels.json  # rewrite only confirmed links
uv run python -m possessed.confirmed path/to/clone --only possessed --remove   # for lists that drop dead entries
uv run python -m possessed.eval path/to/clone/possessed.json my_labels.json   # score four detectors on the same links
```

## How it works

1. Every markdown link is fetched the way a browser follows it: redirects, meta refresh, the
   `window.location` jump a parked domain uses.
2. Triage picks the links worth a model's time: redirected to another domain, a deep link that
   now lands on a homepage, parking or gambling words on the page, or EmbeddingGemma rating the
   live page far from the sentence that cites it. Everything else keeps its green check.
3. Gemma 4, through Ollama's native function calling, chooses its own evidence: the live page, the
   archive capture nearest the day the link was added (`git log -S url`), older captures when that
   one is already the parked page. Then it calls exactly one verdict tool. The loop ends when Ollama
   reports `done_reason: stop`; a reply cut off at the length limit is an error, never a verdict.
4. The gate in `possessed/tools.py` refuses a replacement Gemma did not open in that session, or a
   snapshot that is a bare directory listing or an unrendered JavaScript shell. The refusal goes back
   to the model as a tool error with what to do instead.

Rubric and hard cases are in `possessed/agent.py`; the four evidence tools and four verdict tools in
`possessed/tools.py`; triage in `possessed/triage.py`.

## Results

`results/` holds the full evidence for five awesome lists, each judged by Gemma 4 and second-guessed
by Qwen 3.5 4B, with hand labels where they disagreed and `eval_*.json` scoring four detectors
(status-code checker, URL heuristics, EmbeddingGemma alone, Gemma 4) against those labels. The
numbers are written up in [post/dev-post.md](post/dev-post.md); `check_claims.py` fails when a
figure in that post or this file no longer matches the result files.

Pull requests that came out of it:

- [vuejs/awesome-vue#4593](https://github.com/vuejs/awesome-vue/pull/4593): six entries removed, each
  with the archive capture of what it used to be. One of them, listed in 2018 as a PWA for swapping
  video games, opened a baccarat guide.
- The Action's own PR on a fork of design-resources-for-developers, written by a hosted runner with
  no GPU: see the post.

## License

MIT.
