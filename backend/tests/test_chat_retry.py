"""Regression tests for retrying previous runs."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.models.agent import AgentRun, Message, Thread
from app.services.chat.service import ChatService


def test_build_retry_request_restores_question_attachments_and_requested_mode() -> None:
    """Retry payload should preserve the original user request and requested mode."""

    now = datetime.now(timezone.utc)
    workspace_id = uuid4()
    user_id = uuid4()
    thread_id = uuid4()
    request_message_id = uuid4()
    document_id = uuid4()

    thread = Thread(
        id=thread_id,
        workspace_id=workspace_id,
        created_by=user_id,
        title="Business limits",
        mode="auto",
        status="active",
        latest_run_id=None,
        pinned_document_ids=[],
        metadata_json={"entrypoint": "chat"},
        archived_at=None,
        created_at=now,
        updated_at=now,
    )
    run = AgentRun(
        id=uuid4(),
        thread_id=thread_id,
        workspace_id=workspace_id,
        user_id=user_id,
        request_message_id=request_message_id,
        request_type="kb_qa",
        route_target="rag",
        status="cancelled",
        result_status="cancelled",
        model_name="qwen3-max",
        model_revision=None,
        evidence_grade=None,
        final_answer_message_id=None,
        token_usage_json={},
        metrics_json={},
        started_at=now,
        ended_at=now,
        error_code="RunCancelledError",
        error_message="Run cancelled by user.",
        created_at=now,
    )
    request_message = Message(
        id=request_message_id,
        thread_id=thread_id,
        run_id=None,
        role="user",
        content_text="Business 套餐的单文件大小上限是多少？",
        content_json={},
        sequence_no=1,
        parent_message_id=None,
        metadata_json={
            "attachments": [str(document_id)],
            "requested_mode": "auto",
            "request_metadata": {"entrypoint": "chat"},
        },
        created_at=now,
    )

    payload = ChatService._build_retry_request(run=run, thread=thread, request_message=request_message)

    assert payload.thread_id == thread_id
    assert payload.workspace_id == workspace_id
    assert payload.user_id == user_id
    assert payload.message == "Business 套餐的单文件大小上限是多少？"
    assert payload.attachments == [document_id]
    assert payload.mode == "auto"
    assert payload.metadata["entrypoint"] == "chat"
    assert payload.metadata["retry_of_run_id"] == str(run.id)


def test_build_retry_request_falls_back_to_thread_defaults() -> None:
    """Retry payload should still work when the request message lacks metadata."""

    now = datetime.now(timezone.utc)
    workspace_id = uuid4()
    user_id = uuid4()
    thread_id = uuid4()
    request_message_id = uuid4()
    document_id = uuid4()

    thread = Thread(
        id=thread_id,
        workspace_id=workspace_id,
        created_by=user_id,
        title="Direct chat",
        mode="direct",
        status="active",
        latest_run_id=None,
        pinned_document_ids=[str(document_id)],
        metadata_json={"workspace_mode": "direct"},
        archived_at=None,
        created_at=now,
        updated_at=now,
    )
    run = AgentRun(
        id=uuid4(),
        thread_id=thread_id,
        workspace_id=workspace_id,
        user_id=user_id,
        request_message_id=request_message_id,
        request_type="smalltalk",
        route_target="unknown",
        status="completed",
        result_status="success",
        model_name="qwen3-max",
        model_revision=None,
        evidence_grade="sufficient",
        final_answer_message_id=None,
        token_usage_json={},
        metrics_json={},
        started_at=now,
        ended_at=now,
        error_code=None,
        error_message=None,
        created_at=now,
    )
    request_message = Message(
        id=request_message_id,
        thread_id=thread_id,
        run_id=None,
        role="user",
        content_text="你好，帮我概括一下这个系统。",
        content_json={},
        sequence_no=1,
        parent_message_id=None,
        metadata_json={},
        created_at=now,
    )

    payload = ChatService._build_retry_request(run=run, thread=thread, request_message=request_message)

    assert payload.attachments == [document_id]
    assert payload.mode == "direct"
    assert payload.metadata["workspace_mode"] == "direct"
    assert payload.metadata["retry_of_run_id"] == str(run.id)


def test_build_retry_request_prefers_stored_requested_mode_over_previous_route_target() -> None:
    """Retrying an auto-routed direct run should preserve auto mode so intent classification can run again."""

    now = datetime.now(timezone.utc)
    workspace_id = uuid4()
    user_id = uuid4()
    thread_id = uuid4()
    request_message_id = uuid4()

    thread = Thread(
        id=thread_id,
        workspace_id=workspace_id,
        created_by=user_id,
        title="Project context",
        mode="auto",
        status="active",
        latest_run_id=None,
        pinned_document_ids=[],
        metadata_json={},
        archived_at=None,
        created_at=now,
        updated_at=now,
    )
    run = AgentRun(
        id=uuid4(),
        thread_id=thread_id,
        workspace_id=workspace_id,
        user_id=user_id,
        request_message_id=request_message_id,
        request_type="thread_context",
        route_target="direct",
        status="completed",
        result_status="success",
        model_name="qwen3-max",
        model_revision=None,
        evidence_grade="weak",
        final_answer_message_id=None,
        token_usage_json={},
        metrics_json={},
        started_at=now,
        ended_at=now,
        error_code=None,
        error_message=None,
        created_at=now,
    )
    request_message = Message(
        id=request_message_id,
        thread_id=thread_id,
        run_id=None,
        role="user",
        content_text="请总结一下我当前项目的关键背景",
        content_json={},
        sequence_no=1,
        parent_message_id=None,
        metadata_json={"requested_mode": "auto"},
        created_at=now,
    )

    payload = ChatService._build_retry_request(run=run, thread=thread, request_message=request_message)

    assert payload.mode == "auto"
    assert payload.thread_id == thread_id
