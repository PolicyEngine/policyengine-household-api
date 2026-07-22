"""Shared fake of the ``modal`` SDK for unit tests.

Production code imports ``modal`` lazily inside functions, so patching
``sys.modules["modal"]`` with :func:`install_fake_modal` makes those lazy
imports resolve to the fake. The fake covers the worker-dispatch surface:
``modal.Cls.from_name`` / ``modal.Function.from_name`` lookups (including
the pre-#1528 function-shaped fallback), synchronous ``.remote`` and async
``.spawn.aio()`` / ``.get.aio(timeout=...)`` invocation, and
``modal.exception.NotFoundError``.
"""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass, field
from typing import Any


class FakeModalNotFoundError(Exception):
    """Stands in for ``modal.exception.NotFoundError``."""


@dataclass
class FakeWorkerDispatch:
    """Scripted worker behavior for the fake modal SDK.

    ``results`` holds one entry per successive dispatch: a raw worker result
    dict to return, or an exception instance to raise. The final entry
    repeats once the list is exhausted. When a lookup error is set, the
    corresponding ``from_name`` lookup raises it instead of resolving.
    """

    results: list[Any]
    expected_app_name: str | None = None
    expected_environment_name: str | None = None
    cls_lookup_error: Exception | None = None
    function_lookup_error: Exception | None = None
    calls: int = 0
    get_timeouts: list[float | None] = field(default_factory=list)

    def dispatch(self, payload: dict, timeout: float | None) -> dict:
        self.calls += 1
        self.get_timeouts.append(timeout)
        result = self.results[min(self.calls - 1, len(self.results) - 1)]
        if isinstance(result, Exception):
            raise result
        return result

    def check_lookup(
        self, app_name: str, environment_name: str | None
    ) -> None:
        if self.expected_app_name is not None:
            assert app_name == self.expected_app_name
        if self.expected_environment_name is not None:
            assert environment_name == self.expected_environment_name


def install_fake_modal(monkeypatch, worker: FakeWorkerDispatch) -> None:
    class _SyncAsyncCallable:
        def __init__(self, callback):
            self._callback = callback

        def __call__(self, *args, **kwargs):
            return self._callback(*args, **kwargs)

        async def aio(self, *args, **kwargs):
            return self._callback(*args, **kwargs)

    class _FakeFunctionCall:
        def __init__(self, payload):
            self.get = _SyncAsyncCallable(
                lambda timeout=None: worker.dispatch(payload, timeout)
            )

    class _FakeMethod:
        def __init__(self):
            self.remote = _SyncAsyncCallable(
                lambda payload: worker.dispatch(payload, None)
            )
            self.spawn = _SyncAsyncCallable(_FakeFunctionCall)

    class _FakeInstance:
        def __init__(self):
            self.handle_household_request = _FakeMethod()

    class _FakeCls:
        @staticmethod
        def from_name(app_name, cls_name, environment_name=None):
            assert cls_name == "HouseholdWorker"
            worker.check_lookup(app_name, environment_name)
            if worker.cls_lookup_error is not None:
                raise worker.cls_lookup_error
            return _FakeInstance

    class _FakeFunction:
        @staticmethod
        def from_name(app_name, function_name, environment_name=None):
            assert function_name == "handle_household_request"
            worker.check_lookup(app_name, environment_name)
            if worker.function_lookup_error is not None:
                raise worker.function_lookup_error
            return _FakeMethod()

    fake_modal = types.SimpleNamespace(
        Cls=_FakeCls,
        Function=_FakeFunction,
        exception=types.SimpleNamespace(
            NotFoundError=FakeModalNotFoundError,
        ),
    )
    monkeypatch.setitem(sys.modules, "modal", fake_modal)
