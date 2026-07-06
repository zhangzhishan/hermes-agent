"""Helpers for deterministic topic-summary injection."""

from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path
from typing import Any

from hermes_constants import get_hermes_home

logger = logging.getLogger(__name__)

DEFAULT_TOPIC_CONTEXT_MAX_CHARS = 12_000
_SLUG_TOKEN_RE = re.compile(r"[0-9A-Za-z]+|[\u3400-\u9FFF]+")


def _workspace_root(
    *,
    workspace_root: str | Path | None,
    hermes_home: str | Path | None,
) -> Path:
    if workspace_root is not None:
        return Path(workspace_root)
    if hermes_home is not None:
        return Path(hermes_home) / "workspace"
    return get_hermes_home() / "workspace"


def slugify_topic_chat_name(value: str | None, *, fallback: str | None = None) -> str | None:
    text = (value or "").strip()
    if text:
        normalized = unicodedata.normalize("NFKC", text).lower()
        tokens = _SLUG_TOKEN_RE.findall(normalized)
        if tokens:
            return "-".join(tokens)
    fallback_text = (fallback or "").strip()
    if not fallback_text:
        return None
    normalized_fallback = unicodedata.normalize("NFKC", fallback_text).lower()
    fallback_tokens = _SLUG_TOKEN_RE.findall(normalized_fallback)
    if fallback_tokens:
        return "-".join(fallback_tokens)
    return None


def resolve_topic_context_path(
    *,
    platform: Any,
    chat_id: str | None,
    thread_id: str | None,
    chat_name: str | None = None,
    workspace_root: str | Path | None = None,
    hermes_home: str | Path | None = None,
) -> Path | None:
    if not platform or not chat_id or not thread_id:
        return None

    platform_name = getattr(platform, "value", platform)
    if str(platform_name).lower() != "telegram":
        return None

    chat_slug = slugify_topic_chat_name(chat_name, fallback=str(chat_id))
    if not chat_slug:
        return None

    return (
        _workspace_root(workspace_root=workspace_root, hermes_home=hermes_home)
        / "topics"
        / "telegram"
        / chat_slug
        / f"thread-{thread_id}.md"
    )


def load_topic_context_block(
    *,
    platform: Any,
    chat_id: str | None,
    thread_id: str | None,
    chat_name: str | None = None,
    workspace_root: str | Path | None = None,
    hermes_home: str | Path | None = None,
    max_chars: int = DEFAULT_TOPIC_CONTEXT_MAX_CHARS,
) -> str | None:
    path = resolve_topic_context_path(
        platform=platform,
        chat_id=chat_id,
        thread_id=thread_id,
        chat_name=chat_name,
        workspace_root=workspace_root,
        hermes_home=hermes_home,
    )
    if path is None or not path.is_file():
        return None

    try:
        content = path.read_text(encoding="utf-8").strip()
    except OSError:
        logger.debug("Failed to read topic context file: %s", path, exc_info=True)
        return None

    if not content:
        return None

    truncated = False
    if max_chars > 0 and len(content) > max_chars:
        content = content[:max_chars].rstrip()
        truncated = True

    lines = [
        "## Topic Context",
        "",
        f"Source: `{path}`",
        "",
        content,
    ]
    if truncated:
        lines.extend(
            [
                "",
                f"[Topic context truncated to {max_chars} characters.]",
            ]
        )
    return "\n".join(lines)
