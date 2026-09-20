"""One inference request at a time within ONE backend process.

All LM clients acquire here at the HTTP boundary, never at their caller too.
The lease covers response streaming/consumption and is released on close/error.
This is not coordination between uvicorn workers, containers or external clients.
Health and model-list requests do not use this gate.
"""
from contextlib import contextmanager
import threading
import time
from typing import Callable, Iterator, Optional

LMSTUDIO_MAX_CONCURRENT_REQUESTS = 1
GATE_WAIT_POLL_SECONDS = 1.0
_generation_slots = threading.BoundedSemaphore(LMSTUDIO_MAX_CONCURRENT_REQUESTS)
_owner = threading.local()


@contextmanager
def lmstudio_request_gate(
    on_wait: Optional[Callable[[], None]] = None,
) -> Iterator[float]:
    """Yield seconds spent waiting; optionally report activity while queued.

    A nested acquisition is a programming error, detected before it deadlocks.
    Backoff, prompt building and database work belong outside this context.
    """
    if getattr(_owner, "active", False):
        raise RuntimeError("Nested LM Studio generation gate acquisition")
    started = time.monotonic()
    acquired = _generation_slots.acquire(blocking=False)
    try:
        while not acquired:
            if on_wait is not None:
                on_wait()
            acquired = _generation_slots.acquire(timeout=GATE_WAIT_POLL_SECONDS)
        waited = time.monotonic() - started
        _owner.active = True
        yield waited
    finally:
        if acquired:
            _owner.active = False
            _generation_slots.release()
