"""Bytes-on-disk helpers for every generated artefact.

A generated report is compared byte-for-byte in CI, so a half-written file is
worse than no file: it turns a crashed run into a stale-report failure that looks
like a conformance change. Every writer here goes through a temporary file in the
destination directory followed by :func:`os.replace`, which is atomic within one
filesystem, so a destination is either the previous bytes or the complete new
bytes and never a truncated mixture.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Replace ``path`` with ``data`` atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False)
    try:
        with handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(handle.name, path)
    except BaseException:
        # Never leave the scratch file behind: CI asserts a clean working tree.
        Path(handle.name).unlink(missing_ok=True)
        raise


def atomic_write_text(path: Path, text: str) -> None:
    """Replace ``path`` with ``text`` (UTF-8) atomically."""
    atomic_write_bytes(path, text.encode("utf-8"))


def markdown_document(lines: list[str]) -> str:
    """Join rendered Markdown lines into a document with one trailing newline.

    The renderers append a blank line after each section, which leaves a trailing
    empty entry that ``git diff --check`` reports as a blank line at end of file.
    Trimming it here rather than post-processing the written bytes keeps the
    generator the single source of the artefact's exact content.
    """
    trimmed = list(lines)
    while trimmed and trimmed[-1] == "":
        trimmed.pop()
    return "\n".join(trimmed) + "\n"
