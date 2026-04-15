"""Helpers for cancelling active streamed chat runs."""

from __future__ import annotations

from threading import Event, Lock
from uuid import UUID


class RunCancelledError(RuntimeError):
    """Raised when an active streamed run is cancelled by the user."""


class StreamCancellationRegistry:
    """Track cancellation signals for active streamed runs."""

    def __init__(self) -> None:
        self._signals: dict[str, Event] = {}
        self._lock = Lock()

    def register(self, run_id: UUID) -> Event:
        """Create or replace the cancellation event for one run."""

        signal = Event()
        with self._lock:
            self._signals[str(run_id)] = signal
        return signal

    def cancel(self, run_id: UUID) -> bool:
        """Mark one run as cancelled if it is actively streaming."""

        with self._lock:
            signal = self._signals.get(str(run_id))
        if signal is None:
            return False
        signal.set()
        return True

    def is_cancelled(self, run_id: UUID) -> bool:
        """Check whether one active run has been cancelled."""

        with self._lock:
            signal = self._signals.get(str(run_id))
        return bool(signal and signal.is_set())

    def unregister(self, run_id: UUID) -> None:
        """Drop one run from the active streaming map."""

        with self._lock:
            self._signals.pop(str(run_id), None)


stream_cancellation_registry = StreamCancellationRegistry()
