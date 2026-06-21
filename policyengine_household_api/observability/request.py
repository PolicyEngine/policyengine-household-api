from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from .runtime import OBSERVABILITY_INTERNAL_DISPATCH_HEADER
from .runtime import REQUEST_ID_HEADER
from .runtime import TRACEPARENT_HEADER
from .runtime import RequestObservabilityContext
from .runtime import observability_runtime

__all__ = [
    "OBSERVABILITY_INTERNAL_DISPATCH_HEADER",
    "REQUEST_ID_HEADER",
    "TRACEPARENT_HEADER",
    "RequestObservabilityContext",
    "current_context",
    "record_error",
    "record_event",
    "segment",
    "set_attribute",
    "traceparent_header",
]


def current_context() -> RequestObservabilityContext | None:
    return observability_runtime().current_context()


def set_attribute(key: str, value: Any) -> None:
    observability_runtime().set_attribute(key, value)


def record_error(
    exc: BaseException,
    *,
    handled: bool,
    status_code: int | None = None,
    include_stack: bool = True,
) -> None:
    observability_runtime().record_error(
        exc,
        handled=handled,
        status_code=status_code,
        include_stack=include_stack,
    )


def record_event(event: str, **fields: Any) -> None:
    observability_runtime().record_event(event, **fields)


def traceparent_header() -> str | None:
    return observability_runtime().traceparent_header()


@contextmanager
def segment(name: str, **attrs: Any) -> Iterator[None]:
    with observability_runtime().segment(name, **attrs):
        yield
