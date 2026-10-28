# Possessed, demo script (about 75 seconds)

Record the narration as one take, at a normal talking pace, WAV or M4A, and tell me where the file
is. I capture the screens and cut the video to the narration. Pauses between paragraphs are fine,
they make the cut easier. Every number below is checked by `check_claims.py` against results/.

## Narration

This list has sixty-seven thousand stars and a link checker. The checker is green.

Click Chakra Templates. You get a slot site. The domain expired, someone bought it, and the server
still answers 200. That is the only question a link checker asks.

Possessed runs after the checker. Gemma 4, through Ollama, on the runner, no API key. For every
link the checker passed, it opens the page as it is today and the Internet Archive's capture from
the day the link was added, and decides: fine, moved, possessed, or dead.

It picks its own evidence. And it cannot invent a fix. A replacement the model never opened is
refused by code and sent back to it.

Then it opens one pull request. Every row says what the page was, what it is now, and links the
archived original.

This one went to the maintainers of awesome-vue. Six entries that survived their dead-link cleanup,
because they return 200. One was listed as an app for swapping video games. It opens a baccarat
guide.

Possessed. Open weights, your runner, every Monday.

## Shots, in order

1. github.com/bradtraversy/design-resources-for-developers: the star count, then the green
   link-check badge or the Actions tab with the checker passing.
2. The README's React UI Libraries section, cursor on Chakra Templates, click, the slot site loads.
3. The Possessed workflow run on the fork: the log lines "link checker view", "Gemma 4 will read N
   of the M it passes", then the verdicts appearing one per line.
4. One trace from possessed.json: fetch_live, find_snapshot, read_snapshot, possessed. Then one
   refusal line from the gate and the retry.
5. The pull request the Action opened on the fork: the table, then a click on an archive link and
   the original page from 2022 rendering.
6. vuejs/awesome-vue pull request #4593 in the maintainers' repository: the six rows, the GameVix
   row, then the live gamevix.com redirecting to the baccarat page.
7. Final shot: the pull request page in awesome-vue, held for three seconds, title card over it.

The last shot is the pull request landing in a maintainer's repository, not a number.
