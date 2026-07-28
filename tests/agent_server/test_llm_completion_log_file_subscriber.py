"""Unit tests for LLMCompletionLogFileSubscriber."""

from pathlib import Path

import pytest

from openhands.agent_server.conversation_service import (
    LLMCompletionLogFileSubscriber,
)
from openhands.sdk.event import MessageEvent
from openhands.sdk.event.llm_completion_log import LLMCompletionLogEvent
from openhands.sdk.llm.message import Message, TextContent


@pytest.fixture
def sample_log_event() -> LLMCompletionLogEvent:
    return LLMCompletionLogEvent(
        filename="gpt-4o__1721866400.123-a1b2.json",
        log_data='{"messages": [], "response": {}}',
        model_name="gpt-4o",
        usage_id="main",
    )


@pytest.mark.asyncio
async def test_writes_log_data_to_file(tmp_path: Path, sample_log_event):
    log_dir = tmp_path / "completions"
    subscriber = LLMCompletionLogFileSubscriber(log_dir=log_dir)

    await subscriber(sample_log_event)

    written = log_dir / sample_log_event.filename
    assert written.read_text(encoding="utf-8") == sample_log_event.log_data


@pytest.mark.asyncio
async def test_creates_log_dir_if_missing(tmp_path: Path, sample_log_event):
    log_dir = tmp_path / "nested" / "completions"
    assert not log_dir.exists()
    subscriber = LLMCompletionLogFileSubscriber(log_dir=log_dir)

    await subscriber(sample_log_event)

    assert (log_dir / sample_log_event.filename).exists()


@pytest.mark.asyncio
async def test_ignores_non_matching_event_types(tmp_path: Path):
    log_dir = tmp_path / "completions"
    subscriber = LLMCompletionLogFileSubscriber(log_dir=log_dir)

    message_event = MessageEvent(
        source="user",
        llm_message=Message(role="user", content=[TextContent(text="hi")]),
    )
    await subscriber(message_event)

    assert not log_dir.exists()


@pytest.mark.asyncio
async def test_write_failure_does_not_raise(tmp_path: Path, sample_log_event):
    # Point log_dir at a path that collides with an existing file, so
    # mkdir()/write_text() fail — the subscriber should swallow the error.
    blocking_file = tmp_path / "not_a_dir"
    blocking_file.write_text("occupied")
    subscriber = LLMCompletionLogFileSubscriber(log_dir=blocking_file)

    await subscriber(sample_log_event)  # must not raise
