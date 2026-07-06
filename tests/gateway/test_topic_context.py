from pathlib import Path

from gateway.topic_context import load_topic_context_block, slugify_topic_chat_name


def test_slugify_topic_chat_name_normalizes_ascii_words():
    assert slugify_topic_chat_name("lgd & iKun", fallback="123") == "lgd-ikun"


def test_load_topic_context_block_returns_none_without_thread_id(tmp_path: Path):
    assert (
        load_topic_context_block(
            platform="telegram",
            chat_id="123",
            thread_id=None,
            chat_name="lgd & iKun",
            workspace_root=tmp_path,
        )
        is None
    )


def test_load_topic_context_block_loads_existing_telegram_summary(tmp_path: Path):
    workspace = tmp_path / "workspace"
    topic_file = workspace / "topics" / "telegram" / "lgd-ikun" / "thread-2.md"
    topic_file.parent.mkdir(parents=True)
    topic_file.write_text("Thread summary\n\nImportant context.", encoding="utf-8")

    block = load_topic_context_block(
        platform="telegram",
        chat_id="123",
        thread_id="2",
        chat_name="lgd & iKun",
        workspace_root=workspace,
    )

    assert block is not None
    assert block.startswith("## Topic Context")
    assert str(topic_file) in block
    assert "Thread summary" in block
    assert "Important context." in block


def test_load_topic_context_block_truncates_long_file(tmp_path: Path):
    workspace = tmp_path / "workspace"
    topic_file = workspace / "topics" / "telegram" / "123" / "thread-9.md"
    topic_file.parent.mkdir(parents=True)
    topic_file.write_text("A" * 20, encoding="utf-8")

    block = load_topic_context_block(
        platform="telegram",
        chat_id="123",
        thread_id="9",
        workspace_root=workspace,
        max_chars=10,
    )

    assert block is not None
    assert "AAAAAAAAAA" in block
    assert "truncated" in block.lower()
