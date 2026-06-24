"""Shared helpers for per-object discovery/description metadata (vgi-lint strict).

The ``vgi-lint`` strict profile (0.23.0) expects these on **every** function and
table. Each function/table surfaces them in its ``Meta.tags``:

- ``vgi.title`` (VGI124)          -- human-friendly display name. Must not
  normalize-equal the machine name, or VGI125 fires.
- ``vgi.doc_llm`` (VGI112)         -- a Markdown narrative aimed at an LLM/agent.
- ``vgi.doc_md`` (VGI113)          -- a Markdown narrative aimed at human docs.
- ``vgi.keywords`` (VGI126)        -- comma-separated search terms / synonyms.
- ``vgi.source_url`` (VGI128)      -- link to the implementing source file.

``source_url(file)`` builds the canonical GitHub blob URL for a source file so
every object points at exactly where it is implemented.
"""

from __future__ import annotations

#: Base GitHub blob URL for source files in this repo (pinned to ``main``).
_SOURCE_BASE = "https://github.com/Query-farm/vgi-calendar/blob/main/vgi_calendar"


def source_url(relative_path: str) -> str:
    """Build the ``vgi.source_url`` for a file under ``vgi_calendar/``.

    e.g. ``source_url("scalars.py")``.
    """
    return f"{_SOURCE_BASE}/{relative_path}"


def object_tags(
    title: str,
    doc_llm: str,
    doc_md: str,
    keywords: str,
    relative_path: str,
) -> dict[str, str]:
    """Build the five standard per-object discovery/description tags.

    ``relative_path`` is the implementing file relative to ``vgi_calendar/``.
    """
    return {
        "vgi.title": title,
        "vgi.doc_llm": doc_llm,
        "vgi.doc_md": doc_md,
        "vgi.keywords": keywords,
        "vgi.source_url": source_url(relative_path),
    }
