---
title: "Possessed: your link checker is green, and eight of those links now open a casino"
tags: devchallenge, hf26challenge, gemma, opensource
cover_image: post/cover.png (upload on DEV)
---

*This is a submission for the [Hacktoberfest Open-Source AI Challenge Week 4: Ghost in the Machine](https://dev.to/challenges/hacktoberfest-week4-2026-10-26).*

## What I Built

design-resources-for-developers is a list of links with 67,000 stars. It has a link checker, and the checker passes. Open the React UI Libraries section, click Chakra Templates, and you get a page in Indonesian about which slot games pay out. The domain expired, someone bought it, and the server answers 200, which is the only question a link checker asks.

Eight entries on that list open gambling sites today. Another 24 open a domain-for-sale page, an essay mill, a car detailing shop, or some other company that has nothing to do with the words next to the link. None of them fail the checker.

Possessed is a GitHub Action that runs after your link checker. For every link the checker passed, Gemma 4 opens what the link shows today and the Internet Archive's capture from the day the link was added (`git log -S` finds that commit), reads both next to the sentence that cites the link, and gives one of four verdicts: fine, moved, possessed, dead. A possessed or dead link is replaced with the archived original. A moved link gets its new address. Then it opens one pull request with the fixes and a table that says, for each row, what the page was and what it is now.

Nothing in that pull request is a guess. A verdict that proposes a replacement is refused by code unless the replacement is a page Gemma opened in that session: an archive snapshot it read, or a live URL a link checker would pass. The refusal goes back to the model as a tool error that says what to do instead.

Across 591 judgments on five lists, the gate fired 21 times, and all 21 were my bugs rather than Gemma's: ten were a trailing slash I had stored differently from how the model wrote the URL back, eleven were JavaScript-rendered snapshots my rule mistook for empty pages. Not once did Gemma propose a URL it had not opened. I fixed both bugs, kept the gate, and kept the traces in the result files.

## Demo

[X video]

Two pull requests you can open:

- The one the Action wrote on its own, on a fork of design-resources-for-developers, from a hosted GitHub runner with no GPU: [design-resources-for-developers#1](https://github.com/JonathanSolvesProblems/design-resources-for-developers/pull/1). Seven links, six of them gambling sites, each pointed at the archive capture from the month it was added.
- The one a maintainer actually received, on vuejs/awesome-vue: [#4593](https://github.com/vuejs/awesome-vue/pull/4593). Six entries. One of them was listed in 2018 as a PWA for swapping used video games and today opens a Korean guide to baccarat sites. All six survived the list's dead-link cleanup in January, because they still return 200.

## Code

[github.com/JonathanSolvesProblems/possessed](https://github.com/JonathanSolvesProblems/possessed), MIT.

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
        with: { fetch-depth: 0 }
      - uses: JonathanSolvesProblems/possessed@main
```

That is the whole setup. The runner installs Ollama, pulls `gemma4:e4b` and `embeddinggemma`, reads the links, and opens the PR. Locally, `python -m possessed.repo path/to/clone` does the same thing to a checkout.

## How I Built It

Three open-weight models, all through Ollama, no API key anywhere:

- `gemma4:e4b` judges each link. It calls tools natively, and the loop ends when Ollama reports `done_reason: stop`. A run that stops on `length` is logged as an error, never as a verdict.
- `embeddinggemma` does triage. It embeds the sentence that cites each link and the live page, and the lowest 15 percent of similarities go to Gemma, along with any link that redirected to another domain, landed on a homepage from a deep path, or shows parking or gambling words. On design-resources that turned 1,089 passing links into 194 reads.
- `qwen3.5:4b` is a second judge from a different model family. It gets the same evidence fetched fresh, never sees Gemma's answer, and replies in a fixed JSON shape. Where the two disagree, a hand label decides, checked against the live page and the archive.

Gemma chooses its own evidence. It has `fetch_live`, `find_snapshot`, `list_snapshots` and `read_snapshot`, and four verdict tools. A possessed link usually takes it three or four steps: open the live page, find the capture nearest the day the link was added, read it, decide. When the nearest capture is already the parked page, it lists captures and goes back further.

Here is one judgment as logged, the Chakra Templates link, added to the list on 2022-07-17. Four tool calls, 7.7 seconds on my laptop's GPU:

```
fetch_live(url="https://chakra-templates.dev/")
  -> 200, final_url "https://mainslotresmi.org/",
     title "AGEN338 : Tips Bermain Slot88 & Kumpulan Slot Gacor"

find_snapshot(near_date="2022-07-17")
  -> captured 2022-06-03,
     https://web.archive.org/web/20220603052424/https://chakra-templates.dev/

read_snapshot(timestamp="20220603052424")
  -> 200, title "Chakra Templates",
     text "Templates Page Sections Large Page Sections like Hero, Features ..."

possessed(now_shows="Gambling/betting site (AGEN338)",
          originally="A collection of Chakra UI templates for React projects",
          replacement="https://web.archive.org/web/20220603052424/https://chakra-templates.dev/")
  -> ok. Done with this link.
```

The gate let that replacement through because the third call opened it. Had Gemma written any other URL there, the fourth call would have come back as an error.

The hard part was the rubric. A product that was acquired and now redirects to the buyer is moved if the thing itself still exists there, and possessed if only the brand does: InVision links land on Miro's homepage, and nothing of InVision is there, so they are possessed. A login wall is fine, with "cannot verify" in the reason. Twitter links that land on x.com are fine. The prompt holds those as named examples, because a model this size follows an example better than a definition.

What the models contributed, measured. Four detectors asked the same question about the same 193 links from design-resources: does this link need a fix?

| Detector | Flagged | Right | Precision |
|---|---|---|---|
| Status-code link checker | 0 | 0 | passes everything, by construction |
| URL heuristics (other domain, homepage, parking words) | 65 | 33 | 0.51 |
| EmbeddingGemma similarity alone | 30 | 22 | 0.73 |
| Gemma 4 reading the page | 72 | 55 | 0.76 |

On the possessed verdict alone, Gemma 4 was right on 32 of 39. The heuristics were right on 20 of 65.

Those are precision numbers on purpose. The labels come from where Gemma and Qwen agree, plus hand checks where they do not, so a link both models missed is not in the set and recall cannot be measured this way. I am not claiming it.

What it gets wrong: a GitHub profile listed as a project's author ("Vue 2048 by @pengfu") reads to Gemma as possessed, because the profile is not the project. A promo banner for a new product on Inspira UI read as a takeover. The second judge caught most of these, which is why the confirmed mode I used for the awesome-vue PR only applies fixes both models agree on. The Action by itself applies Gemma's verdicts, and that is why every row in its PR carries the evidence.

Pages behind a bot wall, and empty JavaScript shells, cannot be read without a browser. On design-resources that was 36 of the 1,089 passing links. Possessed counts them and says so in the log, instead of judging a "Just a moment..." page.

On a hosted GitHub runner Gemma reads on the CPU, two to three minutes a link, so the Action has a `limit` input and takes the strongest signals first. The run that opened the PR above took 30 minutes end to end on a 1,245-link list, with the models cached from the run before: fetching every link, EmbeddingGemma embedding a thousand pages, then 18 minutes of Gemma 4 reading eight links. Seven of the eight were gambling or for-sale pages and all seven got the archived original; the eighth, a sound-effects library, was fine and it said so. Its `possessed.json`, with every tool call, is in the repo under `results/design-resources-action/`. On my laptop's GPU the same 194 links took 23 minutes.

[X DEV study section: across the 1,000 most-loved DEV posts, N links a checker passes now open something else; the reach number; the second judge's agreement on flagged links]

## Why Does Open Innovation Matter?

A weekly run over a 1,000-link list is about 200 model reads. On a metered API that is a bill, and awesome lists do not have a card on file. On open weights it is runner minutes, which public repositories get for free, and the same workflow file runs on a self-hosted box in a closet.

The other reason is that a maintainer can read the judge. The rubric Gemma follows is forty lines in `agent.py`. The gate is twenty lines in `tools.py`. If a list wants "a login wall counts as dead", that is a sentence change, and the next weekly run uses it. The evidence is open too: the Internet Archive capture in each row is a public record anyone can click.

## My Agent Session

I built this with Claude Code over four days. It wrote most of the code, and it wrote the first pass of the hand labels: for each link where Gemma and Qwen disagreed, it opened the live page and the archive capture and wrote the verdict and the reason into `results/labels_*.json`. The file says so in its first lines, because a label that does not say who made it is not a label.

The calls were mine. What counts as moved and what counts as possessed, after watching it get InVision wrong. Which lists to send fixes to, and which to leave alone: design-resources-for-developers has outside contributions paused, so nothing went there, and its findings are in this post instead. Before posting I spot-checked [X] of the labels against the live pages myself.

The one piece of the build I would point at: the gate started as a prompt instruction, "never invent a URL". The rules file I keep for agent work says a rule with an objective test goes in code, not in the prompt, so it became twenty lines in `tools.py`. Those twenty lines are what turned up my own two bugs.

## The Spirit of It

A possessed link is a page that died and something else moved into the body. The address is still on the list, people still click it, and what answers is a slot machine wearing the old name.

The week's theme is ghosts, and honoring those who are gone. The fix here is not to forget the page. The entry stays, and the link points at what the page was on the day someone thought it worth sharing, kept by the Internet Archive. For Día de los Muertos you keep a place at the table. The pull request keeps a place on the list.

## Prize Categories

Best Use of Gemma. Gemma 4 is the judge, EmbeddingGemma is the triage, and the ablation table above is what each of them added over a link checker and over plain heuristics.
