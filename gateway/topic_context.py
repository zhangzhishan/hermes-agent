"""Helpers for deterministic, profile-scoped Telegram topic context injection."""

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
_SAFE_COMPONENT_RE = re.compile(r"[^0-9A-Za-z._-]+")


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
    return "-".join(fallback_tokens) if fallback_tokens else None


def _safe_component(value: str) -> str | None:
    component = _SAFE_COMPONENT_RE.sub("_", value.strip()).strip("_")
    return component if component and component not in {".", ".."} else None


def resolve_topic_context_path(
    *,
    platform: Any,
    chat_id: str | None,
    thread_id: str | None,
    chat_name: str | None = None,
    workspace_root: str | Path | None = None,
    hermes_home: str | Path | None = None,
) -> Path | None:
    """Return the canonical path keyed by immutable Telegram chat/thread IDs."""
    del chat_name  # display names are attacker-controlled and not identity
    if not platform or not chat_id or not thread_id:
        return None
    platform_name = getattr(platform, "value", platform)
    if str(platform_name).lower() != "telegram":
        return None
    chat_component = _safe_component(str(chat_id))
    thread_component = _safe_component(str(thread_id))
    if not chat_component or not thread_component:
        return None
    return (
        _workspace_root(workspace_root=workspace_root, hermes_home=hermes_home)
        / "topics"
        / "telegram"
        / chat_component
        / f"thread-{thread_component}.md"
    )


def _legacy_topic_context_path(
    *,
    chat_name: str | None,
    chat_id: str,
    thread_id: str,
    workspace_root: str | Path | None,
    hermes_home: str | Path | None,
) -> Path | None:
    """Old human-readable path, accepted only after frontmatter identity validation."""
    chat_slug = slugify_topic_chat_name(chat_name)
    thread_component = _safe_component(thread_id)
    if not chat_slug or not thread_component:
        return None
    return (
        _workspace_root(workspace_root=workspace_root, hermes_home=hermes_home)
        / "topics"
        / "telegram"
        / chat_slug
        / f"thread-{thread_component}.md"
    )


def _legacy_file_matches_chat_id(path: Path, chat_id: str) -> bool:
    try:
        with path.open("r", encoding="utf-8") as handle:
            prefix = handle.read(4096)
    except (OSError, UnicodeError):
        return False
    pattern = rf"(?m)^chat_id:\s*[\"']?{re.escape(chat_id)}[\"']?\s*$"
    return re.search(pattern, prefix) is not None


def _read_bounded(path: Path, max_chars: int) -> tuple[str, bool] | None:
    try:
        with path.open("r", encoding="utf-8") as handle:
            content = handle.read(max_chars + 1) if max_chars > 0 else handle.read()
    except (OSError, UnicodeError):
        logger.debug("Failed to read topic context file: %s", path, exc_info=True)
        return None
    content = content.strip()
    if not content:
        return None
    truncated = max_chars > 0 and len(content) > max_chars
    return (content[:max_chars].rstrip() if truncated else content), truncated


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
    if path is None:
        return None

    selected = path if path.is_file() else None
    if selected is None and chat_id and thread_id:
        legacy = _legacy_topic_context_path(
            chat_name=chat_name,
            chat_id=str(chat_id),
            thread_id=str(thread_id),
            workspace_root=workspace_root,
            hermes_home=hermes_home,
        )
        if legacy is not None and legacy.is_file() and _legacy_file_matches_chat_id(
            legacy, str(chat_id)
        ):
            selected = legacy
    if selected is None:
        return None

    loaded = _read_bounded(selected, max_chars)
    if loaded is None:
        return None
    content, truncated = loaded
    lines = ["## Topic Context", "", f"Source: `{selected}`", "", content]
    if truncated:
        lines.extend(["", f"[Topic context truncated to {max_chars} characters.]"])
    return "\n".join(lines)
