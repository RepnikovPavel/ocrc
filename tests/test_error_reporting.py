"""Regression test: a failed parse must carry the server's error text.

Incident: an agent parsing arXiv papers through this client hit status=error
and `ocrc` printed only "parsing error" — the status word, with no way to see
the underlying failure. `wait_for` now appends the `error` field the status
endpoint returns, so the next agent can act on the message instead of
blindly retrying.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dont_read_me_src"))
import ocrc  # noqa: E402

SHA = "ab" * 32


def test_wait_for_surfaces_server_error(monkeypatch):
    monkeypatch.setattr(
        ocrc, "_status_with_retry",
        lambda *a, **k: {"status": "error",
                         "error": "ValueError: page did not render"})
    with pytest.raises(SystemExit) as excinfo:
        ocrc.wait_for("http://server", SHA, "prompt_layout_all_en")
    assert "ValueError: page did not render" in str(excinfo.value)


def test_wait_for_error_without_detail_still_exits(monkeypatch):
    """Older servers do not send `error`; the exit must still happen."""
    monkeypatch.setattr(
        ocrc, "_status_with_retry", lambda *a, **k: {"status": "error"})
    with pytest.raises(SystemExit) as excinfo:
        ocrc.wait_for("http://server", SHA, "prompt_layout_all_en")
    assert f"parsing error for {SHA[:12]}" in str(excinfo.value)
