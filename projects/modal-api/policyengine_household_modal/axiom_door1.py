"""Modal plumbing for Door 1 (Axiom rules through policyengine-axiom).

Read docs/axiom-door1-design.md first. Everything here is inert unless the
deploy machine sets ``HOUSEHOLD_AXIOM_DOOR1_PACKAGES``: then the worker image
installs those packages, its environment turns ``axiom_door1.enabled`` on,
and the worker mounts the Door 1 volume.

- The kill switch lives in the Modal Dict ``household-api-axiom-door1``
  (key ``control``), one per Modal environment. Each container mirrors it
  every 30 seconds into a local file that policyengine-axiom re-reads
  (``PE_AXIOM_CONTROL``). A Dict is used, not a Volume, because a running
  container sees another writer's Volume changes only after ``reload()``,
  which fails while files are open.
- Outcome counts (no household values) go to the Volume
  ``household-api-axiom-door1``, one directory per container: a Volume keeps
  the last writer's copy of a file, so containers must not share files.
- ``stage_finished_days`` merges the container directories per UTC day.
  Nothing here sends the counts anywhere.

This module is imported inside worker and canary containers: keep module
scope free of eager work (docs/engineering/skills/modal-images.md).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Deploy machine: a JSON list of pip specs (wheel URLs or files) for
# policyengine-axiom and the rules engine. Unset: Door 1 is not deployed.
PACKAGES_ENV = "HOUSEHOLD_AXIOM_DOOR1_PACKAGES"
# Deploy machine: the bind-time mode baked into the image environment.
MODE_ENV = "HOUSEHOLD_AXIOM_DOOR1_MODE"
DEFAULT_MODE = "shadow"
BIND_MODES = ("shadow", "compare", "on")
# Deploy machine: request selection baked into the image environment, each
# a comma-separated list. Unset: the config file's value applies.
SELECTION_ENVS = {
    "HOUSEHOLD_AXIOM_DOOR1_SERVE_CHANNELS": "AXIOM_DOOR1__SERVE_CHANNELS",
    "HOUSEHOLD_AXIOM_DOOR1_CLIENTS": "AXIOM_DOOR1__CLIENTS",
    "HOUSEHOLD_AXIOM_DOOR1_SHADOW_CHANNELS": "AXIOM_DOOR1__SHADOW_CHANNELS",
}
CHANNEL_SELECTION_ENVS = (
    "HOUSEHOLD_AXIOM_DOOR1_SERVE_CHANNELS",
    "HOUSEHOLD_AXIOM_DOOR1_SHADOW_CHANNELS",
)
CHANNELS = ("current", "frontier")
# Container: set by the image environment when Door 1 is deployed.
ENABLED_ENV = "AXIOM_DOOR1__ENABLED"

CONTROL_DICT_NAME = "household-api-axiom-door1"
CONTROL_DICT_KEY = "control"
CONTROL_MODES = ("off", "shadow", "compare", "on")
CONTROL_POLL_SECONDS = 30.0
LOCAL_CONTROL_PATH = Path("/tmp/axiom-door1-control.json")
# Until the first successful read of the Dict, a container runs capped to
# off: a kill switch set before the container started must hold even when
# the Dict is unreachable.
STARTUP_CONTROL = {"mode": "off"}

SINK_VOLUME_NAME = "household-api-axiom-door1"
SINK_MOUNT = Path("/axiom-door1")
CONTAINER_SINKS = SINK_MOUNT / "sink"
PUBLISH_STAGING = SINK_MOUNT / "publish"
AGGREGATE_PREFIX = "door1-aggregate-"


# ---------------------------------------------------------------------------
# deploy time
# ---------------------------------------------------------------------------


def door1_install_specs(environ: dict[str, str] | None = None) -> list[str]:
    """The packages to install in the worker image; [] means not deployed."""
    environ = os.environ if environ is None else environ
    raw = environ.get(PACKAGES_ENV, "").strip()
    if not raw:
        return []
    try:
        specs = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{PACKAGES_ENV} must be a JSON list") from exc
    if not isinstance(specs, list) or not all(
        isinstance(spec, str) and spec.strip() for spec in specs
    ):
        raise RuntimeError(f"{PACKAGES_ENV} must be a JSON list of strings")
    return [spec.strip() for spec in specs]


def door1_image_env(environ: dict[str, str] | None = None) -> dict[str, str]:
    environ = os.environ if environ is None else environ
    mode = (environ.get(MODE_ENV) or DEFAULT_MODE).strip().lower()
    if mode not in BIND_MODES:
        raise RuntimeError(f"{MODE_ENV} must be one of {BIND_MODES}")
    image_env = {ENABLED_ENV: "true", "AXIOM_DOOR1__MODE": mode}
    for deploy_key, container_key in SELECTION_ENVS.items():
        raw = environ.get(deploy_key) or ""
        names = sorted(
            {name.strip() for name in raw.split(",") if name.strip()}
        )
        if not names:
            continue
        if deploy_key in CHANNEL_SELECTION_ENVS:
            unknown = [name for name in names if name not in CHANNELS]
            if unknown:
                # A misspelt channel would silently select nothing.
                raise RuntimeError(
                    f"{deploy_key} names unknown channel(s) {unknown}; "
                    f"use {CHANNELS}"
                )
        image_env[container_key] = ",".join(names)
    return image_env


def door1_deployed(environ: dict[str, str] | None = None) -> bool:
    """True on the deploy machine when packages are set, and inside a
    container whose image enabled Door 1."""
    environ = os.environ if environ is None else environ
    if environ.get(PACKAGES_ENV, "").strip():
        return True
    return environ.get(ENABLED_ENV, "").strip().lower() == "true"


def door1_volumes() -> dict[str, Any]:
    if not door1_deployed():
        return {}
    import modal

    return {
        str(SINK_MOUNT): modal.Volume.from_name(
            SINK_VOLUME_NAME, create_if_missing=True
        )
    }


# ---------------------------------------------------------------------------
# container runtime: the kill switch mirror
# ---------------------------------------------------------------------------


class ControlMirror:
    """Copy the control from its source into a local file, every interval.

    A failed read keeps the file as it is (the last good control); the file
    starts as ``STARTUP_CONTROL`` until the first good read.
    """

    def __init__(
        self,
        path: Path,
        fetch: Callable[[], Any],
        interval: float = CONTROL_POLL_SECONDS,
    ) -> None:
        self.path = Path(path)
        self.fetch = fetch
        self.interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._failing = False

    def refresh_once(self) -> bool:
        try:
            value = self.fetch()
            payload = {} if value is None else validate_control(value)
        except Exception:
            if not self._failing:
                logger.warning(
                    "Door 1 control read failed; keeping the last control",
                    exc_info=True,
                )
            self._failing = True
            return False
        self._failing = False
        self._write(payload)
        return True

    def start(self) -> "ControlMirror":
        self._write(STARTUP_CONTROL)
        self.refresh_once()
        self._thread = threading.Thread(
            target=self._run, name="axiom-door1-control", daemon=True
        )
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            self.refresh_once()

    def _write(self, payload: dict[str, Any]) -> None:
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(payload, sort_keys=True))
        os.replace(tmp, self.path)


def validate_control(value: Any) -> dict[str, Any]:
    """The control document policyengine-axiom reads: mode cap + deny list."""
    if not isinstance(value, dict):
        raise ValueError("the Door 1 control must be a JSON object")
    unknown = set(value) - {"mode", "deny", "note", "updated_at"}
    if unknown:
        raise ValueError(f"unknown control keys: {sorted(unknown)}")
    out: dict[str, Any] = {}
    mode = value.get("mode")
    if mode is not None:
        mode = str(mode).strip().lower()
        if mode not in CONTROL_MODES:
            raise ValueError(f"mode must be one of {CONTROL_MODES}")
        out["mode"] = mode
    deny = value.get("deny") or []
    if not isinstance(deny, list) or not all(
        isinstance(item, str) and item for item in deny
    ):
        raise ValueError("deny must be a list of variable names")
    if deny:
        out["deny"] = sorted(set(deny))
    return out


def _dict_fetch(modal_environment: str | None) -> Callable[[], Any]:
    def fetch() -> Any:
        import modal

        kwargs = {}
        if modal_environment:
            kwargs["environment_name"] = modal_environment
        control = modal.Dict.from_name(CONTROL_DICT_NAME, **kwargs)
        return control.get(CONTROL_DICT_KEY)

    return fetch


def start_door1_container_runtime(
    *,
    fetch: Callable[[], Any] | None = None,
    control_path: Path = LOCAL_CONTROL_PATH,
    sink_root: Path = CONTAINER_SINKS,
    container_id: str | None = None,
) -> ControlMirror | None:
    """After a snapshot restore: per-container sink, then the control mirror.

    A no-op unless Door 1 bound in this process. Never raises.
    """
    from policyengine_household_api import axiom_door1

    if not axiom_door1.state().bound:
        return None
    try:
        container = (
            container_id or os.getenv("MODAL_TASK_ID") or uuid.uuid4().hex
        )
        axiom_door1.configure_door1_runtime(
            sink_dir=Path(sink_root) / container,
            control_path=control_path,
        )
        mirror = ControlMirror(
            control_path,
            fetch or _dict_fetch(os.getenv("MODAL_ENVIRONMENT")),
        )
        return mirror.start()
    except Exception:
        logger.warning("Door 1 container runtime failed", exc_info=True)
        return None


# ---------------------------------------------------------------------------
# the daily upload
# ---------------------------------------------------------------------------


def stage_finished_days(
    sink_root: Path = CONTAINER_SINKS,
    staging: Path = PUBLISH_STAGING,
    today: str | None = None,
) -> list[str]:
    """Merge every container's file of each finished UTC day into one file.

    A later, separate job can read ``staging``; nothing here sends the
    counts anywhere. Returns the days staged.
    """
    today = today or datetime.now(timezone.utc).date().isoformat()
    by_day: dict[str, list[Path]] = {}
    for path in sorted(Path(sink_root).glob(f"*/{AGGREGATE_PREFIX}*.jsonl")):
        day = path.stem.removeprefix(AGGREGATE_PREFIX)
        if day < today:
            by_day.setdefault(day, []).append(path)
    staging = Path(staging)
    staging.mkdir(parents=True, exist_ok=True)
    for day, paths in sorted(by_day.items()):
        lines = [
            line
            for path in paths
            for line in path.read_text().splitlines()
            if line.strip()
        ]
        target = staging / f"{AGGREGATE_PREFIX}{day}.jsonl"
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_text("".join(f"{line}\n" for line in lines))
        os.replace(tmp, target)
    return sorted(by_day)


# ---------------------------------------------------------------------------
# operator CLI: the kill switch
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Show or set the Door 1 control (the kill switch)."
    )
    parser.add_argument("--modal-environment", required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("show")
    setter = commands.add_parser("set")
    setter.add_argument("--mode", choices=CONTROL_MODES)
    setter.add_argument(
        "--deny", default="", help="comma-separated variable names"
    )
    setter.add_argument("--note", default="")
    commands.add_parser("clear")
    args = parser.parse_args(argv)

    import modal

    control = modal.Dict.from_name(
        CONTROL_DICT_NAME,
        create_if_missing=True,
        environment_name=args.modal_environment,
    )
    if args.command == "set":
        value: dict[str, Any] = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if args.mode:
            value["mode"] = args.mode
        deny = [item.strip() for item in args.deny.split(",") if item.strip()]
        if deny:
            value["deny"] = deny
        if args.note:
            value["note"] = args.note
        validate_control(value)
        control[CONTROL_DICT_KEY] = value
    elif args.command == "clear":
        try:
            control.pop(CONTROL_DICT_KEY)
        except KeyError:
            pass
    print(json.dumps(control.get(CONTROL_DICT_KEY), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
