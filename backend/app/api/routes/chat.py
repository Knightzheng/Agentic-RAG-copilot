"""聊天相关路由。"""

from __future__ import annotations

from queue import Queue
from threading import Thread
from typing import Any, Iterator

import orjson
from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, get_db
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat.service import ChatExecutionError, ChatService
from app.services.chat.stream_control import RunCancelledError, stream_cancellation_registry

router = APIRouter(prefix="/chat")
_STREAM_SENTINEL = object()


@router.post("", response_model=ChatResponse)
def chat(payload: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    """执行一次同步聊天。"""

    try:
        response = ChatService(db).chat(payload)
        db.commit()
        return response
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ChatExecutionError as exc:
        db.commit()
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except RuntimeError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/stream")
def chat_stream(payload: ChatRequest) -> StreamingResponse:
    """执行一次流式聊天，并输出 SSE 事件。"""

    return build_chat_stream_response(payload)


def build_chat_stream_response(payload: ChatRequest) -> StreamingResponse:
    """为单次聊天请求构建流式响应。"""

    return StreamingResponse(
        _iter_chat_stream(payload),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _iter_chat_stream(payload: ChatRequest) -> Iterator[str]:
    event_queue: Queue[str | object] = Queue()
    worker = Thread(target=_run_chat_stream_worker, args=(payload, event_queue), daemon=True)
    worker.start()

    while True:
        item = event_queue.get()
        if item is _STREAM_SENTINEL:
            break
        yield str(item)


def _run_chat_stream_worker(payload: ChatRequest, event_queue: Queue[str | object]) -> None:
    db = SessionLocal()
    prepared = None
    service = None
    current_state: dict[str, Any] = {}
    streamed_answer = ""

    try:
        service = ChatService(db)
        prepared = service.prepare_chat(payload)
        current_state = dict(prepared.initial_state)
        cancel_signal = stream_cancellation_registry.register(prepared.run.id)

        def on_answer_token(delta: str) -> None:
            nonlocal streamed_answer
            if not delta:
                return
            streamed_answer += delta
            _queue_event(
                event_queue,
                "token",
                {
                    "run_id": prepared.run.id,
                    "thread_id": prepared.thread.id,
                    "delta": delta,
                    "answer": streamed_answer,
                },
            )

        def on_step_event(payload_dict: dict[str, Any]) -> None:
            _queue_event(event_queue, "step", payload_dict)

        service.graph_service.set_answer_token_callback(on_answer_token)
        service.graph_service.set_cancel_checker(cancel_signal.is_set)
        service.graph_service.set_step_event_callback(on_step_event)
        db.commit()
        _queue_event(
            event_queue,
            "run_created",
            {
                "run_id": prepared.run.id,
                "thread_id": prepared.thread.id,
                "status": prepared.run.status,
                "question": payload.message,
                "retry_of_run_id": payload.metadata.get("retry_of_run_id"),
            },
        )

        for update in service.graph_service.stream(prepared.initial_state):
            if isinstance(update, dict):
                for step_key, step_output in update.items():
                    if isinstance(step_output, dict):
                        current_state.update(step_output)
            else:
                service.graph_service.summarize_stream_output(update)
            db.commit()

        response = service.complete_chat(prepared=prepared, final_state=current_state)
        db.commit()
        _queue_event(
            event_queue,
            "final",
            {
                **response.model_dump(mode="json"),
                "question": payload.message,
                "retry_of_run_id": payload.metadata.get("retry_of_run_id"),
            },
        )
        _queue_event(
            event_queue,
            "done",
            {
                "run_id": response.run_id,
                "thread_id": response.thread_id,
                "status": response.status,
            },
        )
    except RunCancelledError as exc:
        if prepared is not None and service is not None:
            service.mark_run_cancelled(prepared=prepared, reason=str(exc))
            db.commit()
            _queue_event(
                event_queue,
                "cancelled",
                {
                    "run_id": prepared.run.id,
                    "thread_id": prepared.thread.id,
                    "status": "cancelled",
                    "answer": streamed_answer,
                    "question": payload.message,
                    "retry_of_run_id": payload.metadata.get("retry_of_run_id"),
                },
            )
            _queue_event(
                event_queue,
                "done",
                {
                    "run_id": prepared.run.id,
                    "thread_id": prepared.thread.id,
                    "status": "cancelled",
                },
            )
        else:
            db.rollback()
            _queue_event(event_queue, "error", {"type": "RunCancelledError", "message": str(exc)})
    except ValueError as exc:
        db.rollback()
        _queue_event(event_queue, "error", {"type": "not_found", "message": str(exc)})
    except RuntimeError as exc:
        db.rollback()
        _queue_event(event_queue, "error", {"type": "runtime_error", "message": str(exc)})
    except Exception as exc:  # noqa: BLE001
        if prepared is not None and service is not None:
            service.mark_run_failed(prepared=prepared, exc=exc)
            db.commit()
            _queue_event(
                event_queue,
                "error",
                {
                    "type": type(exc).__name__,
                    "message": str(exc),
                    "run_id": prepared.run.id,
                    "thread_id": prepared.thread.id,
                },
            )
            _queue_event(
                event_queue,
                "done",
                {
                    "run_id": prepared.run.id,
                    "thread_id": prepared.thread.id,
                    "status": "failed",
                },
            )
        else:
            db.rollback()
            _queue_event(event_queue, "error", {"type": type(exc).__name__, "message": str(exc)})
    finally:
        if prepared is not None:
            stream_cancellation_registry.unregister(prepared.run.id)
        if service is not None:
            service.graph_service.set_answer_token_callback(None)
            service.graph_service.set_cancel_checker(None)
            service.graph_service.set_step_event_callback(None)
        db.close()
        event_queue.put(_STREAM_SENTINEL)


def _queue_event(event_queue: Queue[str | object], event: str, data: Any) -> None:
    event_queue.put(_sse_event(event, data))


def _sse_event(event: str, data: Any) -> str:
    payload = orjson.dumps(jsonable_encoder(data)).decode("utf-8")
    return f"event: {event}\ndata: {payload}\n\n"
