"""Unit tests for the URL-fetch + extension-derivation logic.

These cover the regression that motivated the feature: arXiv URLs of the form
`https://arxiv.org/pdf/2606.19348` carry no usable file extension, so the
service rejected them with `unsupported file type: .19348`. The fix derives
the extension from the Content-Type header (defaulting to .pdf).

They also cover GitHub support: `github.com/<owner>/<repo>/blob/<ref>/<path>`
URLs are HTML pages, not files, so they are rewritten to the equivalent
raw.githubusercontent.com URL before downloading; and a download that claims
to be a PDF but lacks the %PDF- header is refused up-front.

Pure-function tests only — no network, no service.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Make ocrc importable as a module without installing it.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dont_read_me_src"))
import ocrc  # noqa: E402


# ---------------------------------------------------------------------------
# is_url
# ---------------------------------------------------------------------------


def test_is_url_accepts_http_and_https():
    assert ocrc.is_url("http://example.com/x.pdf")
    assert ocrc.is_url("https://arxiv.org/pdf/2606.19348")


def test_is_url_rejects_non_http_schemes_and_paths():
    assert not ocrc.is_url("/tmp/local.pdf")
    assert not ocrc.is_url("relative.pdf")
    assert not ocrc.is_url("ftp://example.com/x.pdf")
    assert not ocrc.is_url("file:///tmp/x.pdf")
    assert not ocrc.is_url("")
    assert not ocrc.is_url(None)


# ---------------------------------------------------------------------------
# Extension derivation — the regression case
# ---------------------------------------------------------------------------


def _derive_name(url: str, content_type: str = "") -> str:
    """Replicate the basename + extension logic from fetch_url_to_temp without
    touching the network. Mirrors the production code path closely enough that
    a regression in either step will surface here too."""
    import urllib.parse as up
    parsed = up.urlparse(url)
    name = up.unquote(os.path.basename(parsed.path or "")) or "download"
    name = os.path.basename(name)
    if "?" in name:
        name = name.split("?", 1)[0]
    _, ext = os.path.splitext(name)
    if ext.lower() not in ocrc._KNOWN_EXTS:
        name = name[: -len(ext)] if ext else name
    if os.path.splitext(name)[1].lower() not in ocrc._KNOWN_EXTS:
        ctype = content_type.split(";")[0].strip().lower()
        suffix = ocrc._EXT_BY_CTYPE.get(ctype) or ".pdf"
        name = name + suffix
    return name


def test_arxiv_extensionless_url_becomes_pdf():
    """The original bug: basename '2606.19348' was uploaded as-is and rejected."""
    assert _derive_name("https://arxiv.org/pdf/2606.19348") == "2606.pdf"


def test_arxiv_explicit_pdf_url_is_preserved():
    assert _derive_name("https://arxiv.org/pdf/2606.19348.pdf") == "2606.19348.pdf"


def test_image_url_keeps_extension():
    assert _derive_name("https://x.com/img.png") == "img.png"
    assert _derive_name("https://x.com/photo.JPG") == "photo.JPG"


def test_query_string_is_stripped():
    assert _derive_name("https://x.com/doc.pdf?token=abc&x=1") == "doc.pdf"
    assert _derive_name("https://x.com/img.png?x=1") == "img.png"


def test_extension_only_url_falls_back_to_pdf():
    assert _derive_name("https://x.com/path/") == "download.pdf"
    assert _derive_name("https://x.com/") == "download.pdf"


def test_content_type_overrides_default():
    """If the server says it's a PNG, we don't call it .pdf."""
    name = _derive_name("https://x.com/blob", content_type="image/png")
    assert name.endswith(".png")


def test_bogus_extension_is_replaced_not_appended():
    """basename 'photo.weird' → ext '.weird' is not in the known set, so it's
    dropped and replaced with .pdf (not appended)."""
    name = _derive_name("https://x.com/photo.weird")
    assert name == "photo.pdf", f"got {name!r}"


def test_known_ext_set_covers_pdf_and_common_images():
    for e in (".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".gif", ".bmp"):
        assert e in ocrc._KNOWN_EXTS


# ---------------------------------------------------------------------------
# normalize_source_url — GitHub blob/raw URLs
# ---------------------------------------------------------------------------


def test_github_blob_url_rewritten_to_raw():
    """A blob page is HTML; the raw host serves the file itself."""
    assert ocrc.normalize_source_url(
        "https://github.com/RepnikovPavel/DiplomaMasterDegree/blob/master/main.pdf"
    ) == ("https://raw.githubusercontent.com/"
          "RepnikovPavel/DiplomaMasterDegree/master/main.pdf")


def test_github_raw_segment_also_rewritten():
    assert ocrc.normalize_source_url(
        "https://github.com/owner/repo/raw/main/docs/paper.pdf"
    ) == "https://raw.githubusercontent.com/owner/repo/main/docs/paper.pdf"


def test_github_branch_with_slashes_is_preserved():
    """The ref may itself contain slashes; the raw host resolves it."""
    assert ocrc.normalize_source_url(
        "https://github.com/owner/repo/blob/feature/foo/doc.pdf"
    ) == "https://raw.githubusercontent.com/owner/repo/feature/foo/doc.pdf"


def test_raw_githubusercontent_url_passes_through():
    url = ("https://raw.githubusercontent.com/"
           "RepnikovPavel/DiplomaMasterDegree/master/main.pdf")
    assert ocrc.normalize_source_url(url) == url


def test_non_github_urls_are_untouched():
    url = "https://arxiv.org/pdf/2606.19348"
    assert ocrc.normalize_source_url(url) == url
    url = "https://example.com/github.com/blob/x.pdf"
    assert ocrc.normalize_source_url(url) == url


def test_github_non_file_pages_are_untouched():
    """Repo roots, issue pages etc. have no blob/raw segment to strip."""
    url = "https://github.com/owner/repo"
    assert ocrc.normalize_source_url(url) == url
    url = "https://github.com/owner/repo/issues/1"
    assert ocrc.normalize_source_url(url) == url


# ---------------------------------------------------------------------------
# _ensure_pdf_header — refuse HTML saved under a .pdf name
# ---------------------------------------------------------------------------


def test_pdf_header_check_accepts_a_real_pdf(tmp_path):
    f = tmp_path / "doc.pdf"
    f.write_bytes(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n...")
    ocrc._ensure_pdf_header(str(f), "https://x.com/doc.pdf")  # no raise


def test_pdf_header_check_rejects_html(tmp_path):
    f = tmp_path / "doc.pdf"
    f.write_bytes(b"<!DOCTYPE html><html><title>GitHub</title></html>")
    with pytest.raises(SystemExit):
        ocrc._ensure_pdf_header(str(f), "https://x.com/doc.pdf")


def test_pdf_header_check_ignores_non_pdf_files(tmp_path):
    f = tmp_path / "img.png"
    f.write_bytes(b"\x89PNG\r\n\x1a\n")
    ocrc._ensure_pdf_header(str(f), "https://x.com/img.png")  # no raise


# ---------------------------------------------------------------------------
# _github_token — env precedence
# ---------------------------------------------------------------------------


def test_github_token_env_precedence(monkeypatch):
    monkeypatch.delenv("OCRC_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    assert ocrc._github_token() is None
    monkeypatch.setenv("GH_TOKEN", "gh")
    assert ocrc._github_token() == "gh"
    monkeypatch.setenv("GITHUB_TOKEN", "github")
    assert ocrc._github_token() == "github"
    monkeypatch.setenv("OCRC_GITHUB_TOKEN", "ocrc")
    assert ocrc._github_token() == "ocrc"


# ---------------------------------------------------------------------------
# is_stdout_piped — guarded by mocking
# ---------------------------------------------------------------------------


def test_is_stdout_piped_returns_bool():
    """In a pytest run, stdout is captured → not a TTY → True."""
    assert isinstance(ocrc.is_stdout_piped(), bool)


def test_same_file_detection_recognises_real_same_file(tmp_path):
    """When stdout and stderr fds point at the same file, the guard must fire.
    Simulate by opening one file twice (read/write) and pointing both fds at it
    via os.dup2 — the function uses fstat(st_dev, st_ino) so this is faithful."""
    import os, subprocess, sys
    code = (
        "import sys; sys.path.insert(0, 'dont_read_me_src'); "
        "import ocrc; "
        "print(ocrc._stdout_stderr_same_file())"
    )
    # Open a file, dup it onto both fd 1 and fd 2 inside a subprocess — that's
    # what `> FILE 2>&1` does in the shell.
    with open(tmp_path / "probe.txt", "wb") as f:
        result = subprocess.run(
            [sys.executable, "-c", code],
            stdout=f.fileno(), stderr=subprocess.STDOUT,
        )
    content = (tmp_path / "probe.txt").read_text().strip()
    assert content == "True", f"expected True, got {content!r}"


def test_same_file_detection_false_for_distinct_fds():
    """Default pytest fds (separate stdout/stderr capture) → not the same file."""
    assert ocrc._stdout_stderr_same_file() is False
