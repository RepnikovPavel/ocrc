# How ocrc works

ocrc is a thin client. All the work happens in the dots.mocr service; this file
explains what it asks for and why the shape is what it is.

## Why standard library only

An agent should be able to drop one file on an arbitrary machine and call it. A
dependency means a virtualenv, a pip that may be absent or pinned differently,
and a failure mode that appears only on the machine you cannot debug. The cost is
that `urllib` has no multipart support, so `_multipart()` encodes the body by
hand — about thirty lines, paid once.

## The service API it speaks

All under `/api/v1`:

| call | purpose |
|---|---|
| `POST /documents` | submit a file; answers `queued` or `cached` |
| `GET /documents/{sha256}` | status, progress, tokens, seconds |
| `GET /documents/{sha256}/bundle` | the result as one ZIP |
| `GET /documents?q=` | full-text search |
| `GET /queue` | waiting tasks, in order, with agent names |
| `GET /events` | Server-Sent Events for the same queue |
| `GET /stats` | store size, cache reuse, engine state |

## Deduplication

The service keys a result on three things: the SHA-256 of the uploaded bytes, the
prompt mode, and the page selection. All three change the answer, so all three
are part of the key. A resubmission of the same triple never re-runs the model.

ocrc computes no hashes itself — the server does it on the bytes it received,
which is the only version that can be trusted to match what was parsed.

## Why a ZIP rather than a directory of URLs

The parse produces markdown that links pictures relatively (`images/foo.png`).
Handing back a list of URLs would make the agent reassemble that structure to
render or read the document. One archive with the structure already correct
unpacks into something that renders as-is.

`meta.json` inside carries the sha256, prompt mode, page count, token count and
seconds, so a result folder is self-describing after it leaves the client.

## Waiting

`parse` polls `GET /documents/{sha}` every 3 s and prints progress to stderr when
it changes. `--no-wait` returns immediately with `status=queued`; the caller can
come back with `ocrc parse` on the same file later, which will find it cached.

`watch` holds the SSE stream instead, which emits only on change plus a
keep-alive, so an idle watcher costs nothing.

## Safety note on the archive

The ZIP comes from a service you configured, but `zipfile.extractall` on
untrusted input is a path-traversal hazard in general, so ocrc rejects any entry
that is absolute or contains `..` before extracting. It costs one loop and
removes the class of bug entirely.

## Exit codes

`0` success · `2` usage error · non-zero with a message on stderr otherwise.
Server errors carry the server's own message, not just a status code — a bare
"400 Bad Request" is not something an agent can act on.
