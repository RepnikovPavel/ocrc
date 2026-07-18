# ocrc

Order PDF and image parsing from a [dots.mocr](https://github.com/RepnikovPavel/ocr)
service. One Python file, standard library only, deterministic TSV on stdout.

Written for agents: `prompt.txt` is a low-token brief you can drop straight into
an agent's context.

## Install

```sh
curl -fsSL https://raw.githubusercontent.com/RepnikovPavel/ocrc/main/install.sh | sh
```

No pip, no virtualenv, no dependencies — it copies a single file onto your PATH.
Needs `python3 >= 3.8` and a reachable service.

```sh
export OCRC_SERVER=http://127.0.0.1:8601      # or pass --server
```

## Use

```sh
ocrc parse paper.pdf                    # parse, wait, unpack into ./ocrc-out
ocrc parse paper.pdf --pages 0,1,2      # 0-based selection
ocrc parse a.pdf b.pdf --out /tmp/x     # several at once
ocrc parse paper.pdf --no-wait          # queue and return

ocrc queue                              # who is waiting, in order
ocrc watch                              # follow the queue as events arrive
ocrc search "attention"                 # full-text over everything parsed
ocrc stats                              # store size, cache reuse, engine state
```

Output is TSV, so it composes:

```sh
ocrc parse paper.pdf | cut -f6          # path to document.md
ocrc queue | awk -F'\t' '$7=="running"' # what is running right now
```

stdout carries only the data. Progress and errors go to stderr.

## What comes back

```
ocrc-out/540e8c6cf387/
├── document.md        markdown, with relative links to the images below
├── images/            picture crops the markdown references
├── layout/            per-page layout JSON (bboxes, categories)
└── meta.json          sha256, prompt mode, pages, tokens, seconds
```

The links inside `document.md` resolve inside the folder, so it renders as-is.

## Repeat requests are free

The service keys results on the SHA-256 of the file plus the prompt mode and the
page selection. Asking again for something already parsed is a lookup:

```
first request   27.6 s      status=parsed
same request     0.17 s     status=cached
```

So prefer resubmitting over caching results yourself — and several agents asking
for the same paper cost one parse between them.

## Working alongside other agents

`ocrc queue` shows every waiting task with the name of the agent that submitted
it, so you can see whether someone already queued the document you want.
`ocrc watch` streams the same information over Server-Sent Events, without
polling. Pass `--agent NAME` (or set `OCRC_AGENT`) so others can see who you are.

## Environment

| variable | meaning | default |
|---|---|---|
| `OCRC_SERVER` | service base URL | `http://127.0.0.1:8601` |
| `OCRC_PROMPT_MODE` | default prompt mode | `prompt_layout_all_en` |
| `OCRC_AGENT` | name shown in the queue | `ocrc/$USER` |
| `OCRC_TIMEOUT` | seconds for ordinary calls | `60` |

Uploads and downloads use a longer timeout regardless, because a large PDF
should not fail on the same clock as a status check.

## Layout

- `dont_read_me_src/` — the implementation (one file)
- `if_necessary_you_can_read_me/` — how it works, and the service API it speaks
- `read_me_if_it_is_not_installed/` — installing without the one-liner
- `prompt.txt` — the agent brief

## License

0BSD. See LICENSE.
