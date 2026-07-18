#!/usr/bin/env python3
"""ocrc — order PDF parsing from a dots.mocr service.

Standard library only, on purpose: an agent should be able to drop this file on
any machine with python3 and call it, with no virtualenv, no pip and no version
skew to reason about. That rules out requests/httpx, so multipart bodies are
built by hand below.

Output is deterministic TSV on stdout, one row per submitted document, so a shell
or an LLM can parse it without a JSON library. Anything that is not a result —
progress, waiting, errors — goes to stderr and never pollutes the data stream.
"""

import argparse
import hashlib
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from pathlib import Path

__version__ = "0.1.0"

DEFAULT_SERVER = os.environ.get("OCRC_SERVER", "http://127.0.0.1:8601")
DEFAULT_MODE = os.environ.get("OCRC_PROMPT_MODE", "prompt_layout_all_en")
DEFAULT_AGENT = os.environ.get("OCRC_AGENT") or f"ocrc/{os.environ.get('USER', 'agent')}"
TIMEOUT = float(os.environ.get("OCRC_TIMEOUT", "60"))


def log(message):
    """Progress goes to stderr so stdout stays a clean TSV stream."""
    print(message, file=sys.stderr, flush=True)


# --------------------------------------------------------------------------
# transport (stdlib only)
# --------------------------------------------------------------------------

def _multipart(fields, file_field=None):
    """Encode a multipart/form-data body.

    urllib has no multipart support, and pulling in requests would break the
    "one file, no dependencies" property that makes this installable anywhere.
    """
    boundary = uuid.uuid4().hex
    body = bytearray()
    for name, value in fields.items():
        if value is None:
            continue
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
        body += f"{value}\r\n".encode()
    if file_field:
        name, path = file_field
        filename = Path(path).name
        ctype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        body += f"--{boundary}\r\n".encode()
        body += (f'Content-Disposition: form-data; name="{name}"; '
                 f'filename="{filename}"\r\n').encode()
        body += f"Content-Type: {ctype}\r\n\r\n".encode()
        body += Path(path).read_bytes()
        body += b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return bytes(body), f"multipart/form-data; boundary={boundary}"


def _request(url, data=None, content_type=None, timeout=TIMEOUT, raw=False):
    request = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    if content_type:
        request.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read()
            return payload if raw else json.loads(payload.decode())
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")[:400]
        try:
            detail = json.loads(detail).get("detail", detail)
        except ValueError:
            pass
        raise SystemExit(f"ocrc: server returned {error.code}: {detail}")
    except urllib.error.URLError as error:
        raise SystemExit(
            f"ocrc: cannot reach {url}: {error.reason}\n"
            f"      set OCRC_SERVER or pass --server (currently {DEFAULT_SERVER})")


# --------------------------------------------------------------------------
# operations
# --------------------------------------------------------------------------

def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def submit(server, path, mode, pages, agent):
    fields = {"prompt_mode": mode, "pages": pages, "agent": agent}
    body, ctype = _multipart(fields, file_field=("file", path))
    # a big PDF upload deserves longer than a status call
    return _request(f"{server}/api/v1/documents", body, ctype, timeout=max(TIMEOUT, 300))


def status(server, sha256, mode):
    query = urllib.parse.urlencode({"prompt_mode": mode})
    return _request(f"{server}/api/v1/documents/{sha256}?{query}")


def wait_for(server, sha256, mode, poll=3.0, quiet=False):
    """Block until the document is parsed, reporting progress to stderr."""
    last = None
    while True:
        state = status(server, sha256, mode)
        if state.get("cached") or state.get("status") == "done":
            return state
        if state.get("status") in {"error", "cancelled"}:
            raise SystemExit(f"ocrc: parsing {state['status']} for {sha256[:12]}")
        progress = state.get("progress") or {}
        line = f"{progress.get('done', 0)}/{progress.get('total', '?')}"
        if not quiet and line != last:
            log(f"ocrc: {sha256[:12]} {state.get('status')} {line}")
            last = line
        time.sleep(poll)


def fetch_bundle(server, sha256, mode, out_dir, extract=True):
    query = urllib.parse.urlencode({"prompt_mode": mode})
    payload = _request(f"{server}/api/v1/documents/{sha256}/bundle?{query}",
                       timeout=max(TIMEOUT, 300), raw=True)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    archive = out_dir / f"{sha256[:12]}.zip"
    archive.write_bytes(payload)
    if not extract:
        return archive, None
    target = out_dir / sha256[:12]
    with zipfile.ZipFile(archive) as bundle:
        # the archive is built by this service and contains only relative paths,
        # but a zip is untrusted input in general: refuse anything that escapes
        for name in bundle.namelist():
            if name.startswith("/") or ".." in Path(name).parts:
                raise SystemExit(f"ocrc: refusing unsafe path in bundle: {name}")
        bundle.extractall(target)
    archive.unlink()
    return target, target / "document.md"


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def cmd_parse(args):
    rows = []
    for path in args.paths:
        if not Path(path).is_file():
            raise SystemExit(f"ocrc: no such file: {path}")
        submitted = submit(args.server, path, args.prompt_mode, args.pages, args.agent)
        sha256 = submitted["sha256"]
        cached = submitted["status"] == "cached"
        if not cached and not args.no_wait:
            wait_for(args.server, sha256, args.prompt_mode, quiet=args.quiet)
        elif not cached:
            rows.append((Path(path).name, sha256, "queued", "", "", ""))
            continue

        out, markdown = fetch_bundle(args.server, sha256, args.prompt_mode,
                                     args.out, extract=not args.zip)
        state = status(args.server, sha256, args.prompt_mode)
        rows.append((
            Path(path).name, sha256,
            "cached" if cached else "parsed",
            str(state.get("num_pages") or ""),
            str(state.get("generated_tokens") or ""),
            str(markdown or out),
        ))
    emit(["file", "sha256", "status", "pages", "tokens", "output"], rows)


def cmd_queue(args):
    data = _request(f"{args.server}/api/v1/queue")
    rows = [(str(t["position"]), t["task_id"], t.get("agent") or "-",
             (t.get("sha256") or "-")[:12], t["prompt_mode"], str(t["pages"]), t["status"])
            for t in data["queue"]]
    emit(["position", "task", "agent", "sha256", "mode", "pages", "status"], rows)


def cmd_watch(args):
    """Follow the queue as a live stream, one TSV row per change."""
    url = f"{args.server}/api/v1/events"
    printed_header = False
    try:
        with urllib.request.urlopen(url, timeout=None) as response:
            for raw in response:
                line = raw.decode(errors="replace").rstrip()
                if not line.startswith("data:"):
                    continue
                event = json.loads(line[5:])
                if not printed_header:
                    print("\t".join(["task", "agent", "sha256", "status", "done", "total"]))
                    printed_header = True
                for task in event["queue"]:
                    progress = task.get("progress") or {}
                    print("\t".join([
                        task["task_id"], task.get("agent") or "-",
                        (task.get("sha256") or "-")[:12], task["status"],
                        str(progress.get("done", "")), str(progress.get("total", "")),
                    ]), flush=True)
    except KeyboardInterrupt:
        pass
    except urllib.error.URLError as error:
        raise SystemExit(f"ocrc: cannot stream events: {error.reason}")


def cmd_search(args):
    query = urllib.parse.urlencode({"q": args.query, "limit": args.limit})
    data = _request(f"{args.server}/api/v1/documents?{query}")
    rows = [(r.get("sha256", "")[:12], r.get("filename", ""), r.get("prompt_mode", ""),
             (r.get("snippet") or "").replace("\t", " ").replace("\n", " ")[:120])
            for r in data["results"]]
    emit(["sha256", "file", "mode", "snippet"], rows)


def cmd_stats(args):
    data = _request(f"{args.server}/api/v1/stats")
    store, worker = data["store"], data["worker"]
    rows = [
        ("documents", str(store["documents"])),
        ("submissions", str(store["submissions"])),
        ("cached_results", str(store["cached_results"])),
        ("reuse_ratio", str(store["reuse_ratio"])),
        ("bytes", str(store["bytes"])),
        ("engine", str(worker.get("engine", ""))),
        ("model_state", str(worker.get("model_state", ""))),
    ]
    emit(["key", "value"], rows)


def emit(header, rows):
    print("\t".join(header))
    for row in rows:
        print("\t".join(str(cell) for cell in row))


# --------------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(
        prog="ocrc",
        description="Order PDF/image parsing from a dots.mocr service. TSV on stdout.")
    parser.add_argument("--server", default=DEFAULT_SERVER,
                        help=f"service base URL (default {DEFAULT_SERVER}, env OCRC_SERVER)")
    parser.add_argument("--version", action="version", version=f"ocrc {__version__}")
    sub = parser.add_subparsers(dest="command")

    parse = sub.add_parser("parse", help="parse documents and download the result")
    parse.add_argument("paths", nargs="+", help="PDF or image files")
    parse.add_argument("--prompt-mode", default=DEFAULT_MODE, dest="prompt_mode")
    parse.add_argument("--pages", default=None, help="0-based, e.g. 0,1,2 (default: all)")
    parse.add_argument("--out", default="./ocrc-out", help="where to put results")
    parse.add_argument("--agent", default=DEFAULT_AGENT, help="name shown in the queue")
    parse.add_argument("--no-wait", action="store_true", help="queue and exit")
    parse.add_argument("--zip", action="store_true", help="keep the archive instead of unpacking")
    parse.add_argument("--quiet", "-q", action="store_true", help="no progress on stderr")
    parse.set_defaults(func=cmd_parse)

    queue = sub.add_parser("queue", help="who is waiting, in order")
    queue.set_defaults(func=cmd_queue)

    watch = sub.add_parser("watch", help="follow the queue as events arrive")
    watch.set_defaults(func=cmd_watch)

    search = sub.add_parser("search", help="full-text search over parsed documents")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=20)
    search.set_defaults(func=cmd_search)

    stats = sub.add_parser("stats", help="store size and cache reuse")
    stats.set_defaults(func=cmd_stats)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help(sys.stderr)
        return 2
    args.server = args.server.rstrip("/")
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
