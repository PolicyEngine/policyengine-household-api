"""Door 1 Modal plumbing: inert by default, fail-closed kill switch."""

import importlib
import inspect
import json
import sys
import types

import pytest

from policyengine_household_api import axiom_door1 as host_door1
from policyengine_household_modal import axiom_door1


pytestmark = pytest.mark.usefixtures("door1_reset")


# deploy time ----------------------------------------------------------------


def test_door1_is_not_deployed_by_default():
    assert axiom_door1.door1_install_specs({}) == []
    assert axiom_door1.door1_deployed({}) is False


def test_install_specs_come_from_a_json_list():
    environ = {
        axiom_door1.PACKAGES_ENV: json.dumps(
            ["policyengine-axiom @ https://example.test/pa.whl"]
        )
    }

    assert axiom_door1.door1_install_specs(environ) == [
        "policyengine-axiom @ https://example.test/pa.whl"
    ]
    assert axiom_door1.door1_deployed(environ) is True


@pytest.mark.parametrize("raw", ["not json", '"a string"', "[1]", '[""]'])
def test_install_specs_reject_anything_but_a_list_of_strings(raw):
    with pytest.raises(RuntimeError):
        axiom_door1.door1_install_specs({axiom_door1.PACKAGES_ENV: raw})


def test_image_env_turns_door1_on_in_shadow_by_default():
    assert axiom_door1.door1_image_env({}) == {
        "AXIOM_DOOR1__ENABLED": "true",
        "AXIOM_DOOR1__MODE": "shadow",
    }
    with pytest.raises(RuntimeError):
        axiom_door1.door1_image_env({axiom_door1.MODE_ENV: "strict"})


def test_image_env_carries_the_selection_tiers():
    environ = {
        axiom_door1.MODE_ENV: "compare",
        "HOUSEHOLD_AXIOM_DOOR1_SERVE_CHANNELS": "frontier",
        "HOUSEHOLD_AXIOM_DOOR1_CLIENTS": " b-client, a-client ,b-client",
        "HOUSEHOLD_AXIOM_DOOR1_SHADOW_CHANNELS": "frontier",
    }

    assert axiom_door1.door1_image_env(environ) == {
        "AXIOM_DOOR1__ENABLED": "true",
        "AXIOM_DOOR1__MODE": "compare",
        "AXIOM_DOOR1__SERVE_CHANNELS": "frontier",
        "AXIOM_DOOR1__CLIENTS": "a-client,b-client",
        "AXIOM_DOOR1__SHADOW_CHANNELS": "frontier",
    }


def test_image_env_leaves_out_empty_selection_values():
    environ = {
        "HOUSEHOLD_AXIOM_DOOR1_CLIENTS": " , ",
        "HOUSEHOLD_AXIOM_DOOR1_SHADOW_CHANNELS": "",
    }

    assert axiom_door1.door1_image_env(environ) == {
        "AXIOM_DOOR1__ENABLED": "true",
        "AXIOM_DOOR1__MODE": "shadow",
    }


@pytest.mark.parametrize(
    "key",
    [
        "HOUSEHOLD_AXIOM_DOOR1_SERVE_CHANNELS",
        "HOUSEHOLD_AXIOM_DOOR1_SHADOW_CHANNELS",
    ],
)
def test_image_env_rejects_a_misspelt_channel(key):
    with pytest.raises(RuntimeError, match="unknown channel"):
        axiom_door1.door1_image_env({key: "frontier,fronteir"})


def _record_worker_image(monkeypatch, environ):
    from policyengine_household_modal import images

    calls = []

    class FakeImage:
        def __getattr__(self, name):
            def step(*args, **kwargs):
                calls.append((name, args, kwargs))
                return self

            return step

    monkeypatch.setattr(
        images.modal.Image,
        "debian_slim",
        lambda *args, **kwargs: FakeImage(),
    )
    for key in (
        axiom_door1.PACKAGES_ENV,
        axiom_door1.MODE_ENV,
        *axiom_door1.SELECTION_ENVS,
    ):
        monkeypatch.delenv(key, raising=False)
    for key, value in environ.items():
        monkeypatch.setenv(key, value)
    images.household_api_worker_image()
    return calls


def test_worker_image_is_unchanged_without_door1_packages(monkeypatch):
    calls = _record_worker_image(monkeypatch, {})

    assert not [
        call
        for call in calls
        if call[2].get("extra_options") == "--no-deps"
        or "AXIOM_DOOR1__ENABLED" in json.dumps(call[1], default=str)
    ]


def test_worker_image_installs_door1_without_touching_the_locked_pins(
    monkeypatch,
):
    calls = _record_worker_image(
        monkeypatch,
        {
            axiom_door1.PACKAGES_ENV: json.dumps(["pa.whl", "engine.whl"]),
            axiom_door1.MODE_ENV: "compare",
        },
    )

    install = calls.index(
        (
            "uv_pip_install",
            ("pa.whl", "engine.whl"),
            {"uv_version": "0.13.6", "extra_options": "--no-deps"},
        )
    )
    assert calls[install + 1] == (
        "env",
        ({"AXIOM_DOOR1__ENABLED": "true", "AXIOM_DOOR1__MODE": "compare"},),
        {},
    )
    step_names = [call[0] for call in calls]
    assert install < step_names.index("add_local_python_source")


# worker app -----------------------------------------------------------------


@pytest.fixture
def worker_app(monkeypatch):
    monkeypatch.setenv("MODAL_ENVIRONMENT", "testing")
    from policyengine_household_modal import worker_app

    return importlib.reload(worker_app)


def test_worker_mounts_no_volume_by_default(worker_app, monkeypatch):
    monkeypatch.delenv(axiom_door1.ENABLED_ENV, raising=False)
    monkeypatch.delenv(axiom_door1.PACKAGES_ENV, raising=False)

    options = worker_app.worker_function_options(modal_environment="main")

    assert "volumes" not in options


def test_door1_worker_mounts_the_count_volume(worker_app, monkeypatch):
    monkeypatch.setenv(axiom_door1.ENABLED_ENV, "true")
    monkeypatch.setattr(
        worker_app.modal.Volume,
        "from_name",
        lambda name, **kwargs: ("volume", name, kwargs),
    )

    options = worker_app.worker_function_options(modal_environment="main")

    assert options["volumes"] == {
        "/axiom-door1": (
            "volume",
            "household-api-axiom-door1",
            {"create_if_missing": True},
        )
    }


def test_snapshot_hook_binds_door1_before_the_prewarm(worker_app):
    """The prewarmed caches and the bound system both ride the snapshot;
    binding first means the snapshot holds the bound system."""
    source = inspect.getsource(worker_app)

    assert source.index("bind_door1()") < source.index(
        "prewarm_parameter_caches()"
    )


def test_worker_flushes_counts_at_exit(worker_app):
    assert hasattr(worker_app.HouseholdWorker, "flush_door1_counts")


def test_container_runtime_is_a_no_op_when_door1_is_not_bound():
    fetches = []

    mirror = axiom_door1.start_door1_container_runtime(
        fetch=lambda: fetches.append(True)
    )

    assert mirror is None
    assert fetches == []


# the kill switch mirror -----------------------------------------------------


def test_mirror_starts_capped_off_until_the_first_good_read(tmp_path):
    path = tmp_path / "control.json"
    mirror = axiom_door1.ControlMirror(path, fetch=_raise, interval=3600)

    mirror.start()
    mirror.stop()

    assert json.loads(path.read_text()) == {"mode": "off"}


def test_mirror_copies_the_control_and_keeps_the_last_good_one(tmp_path):
    path = tmp_path / "control.json"
    values = [{"mode": "shadow", "deny": ["snap"], "note": "x"}]
    mirror = axiom_door1.ControlMirror(path, fetch=lambda: values[0])

    assert mirror.refresh_once() is True
    assert json.loads(path.read_text()) == {
        "deny": ["snap"],
        "mode": "shadow",
    }

    values[0] = {"mode": "max"}
    assert mirror.refresh_once() is False
    mirror.fetch = _raise
    assert mirror.refresh_once() is False
    assert json.loads(path.read_text())["mode"] == "shadow"

    mirror.fetch = lambda: None
    assert mirror.refresh_once() is True
    assert json.loads(path.read_text()) == {}


def _raise():
    raise ConnectionError("Modal Dict unreachable")


def test_container_runtime_gives_each_container_its_own_sink(
    monkeypatch, tmp_path
):
    configured = {}
    monkeypatch.setattr(
        host_door1,
        "_state",
        host_door1.Door1State(
            bound_countries=frozenset({"us"}), runtime=object()
        ),
    )
    monkeypatch.setattr(
        host_door1,
        "configure_door1_runtime",
        lambda **kwargs: configured.update(kwargs),
    )

    mirror = axiom_door1.start_door1_container_runtime(
        fetch=lambda: {"mode": "compare"},
        control_path=tmp_path / "control.json",
        sink_root=tmp_path / "sink",
        container_id="ta-123",
    )
    mirror.stop()

    assert configured == {
        "sink_dir": tmp_path / "sink" / "ta-123",
        "control_path": tmp_path / "control.json",
    }
    assert json.loads((tmp_path / "control.json").read_text()) == {
        "mode": "compare"
    }


# the daily upload -----------------------------------------------------------


def test_stage_finished_days_merges_containers_and_skips_today(tmp_path):
    sink = tmp_path / "sink"
    for container, day, line in [
        ("a", "2026-11-06", '{"n": 1}'),
        ("b", "2026-11-06", '{"n": 2}'),
        ("a", "2026-11-07", '{"n": 3}'),
        ("a", "2026-11-08", '{"n": 4}'),
    ]:
        directory = sink / container
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / f"door1-aggregate-{day}.jsonl").open("a") as f:
            f.write(line + "\n")

    staged = axiom_door1.stage_finished_days(
        sink, tmp_path / "publish", today="2026-11-08"
    )

    assert staged == ["2026-11-06", "2026-11-07"]
    merged = tmp_path / "publish" / "door1-aggregate-2026-11-06.jsonl"
    assert merged.read_text().splitlines() == ['{"n": 1}', '{"n": 2}']
    assert not (
        tmp_path / "publish" / "door1-aggregate-2026-11-08.jsonl"
    ).exists()


# operator CLI ---------------------------------------------------------------


def test_cli_sets_and_clears_the_control(monkeypatch, capsys):
    store = {}

    class FakeDict(dict):
        pass

    fake_dict = FakeDict()

    def from_name(name, **kwargs):
        store["lookup"] = (name, kwargs)
        return fake_dict

    fake_modal = types.SimpleNamespace(
        Dict=types.SimpleNamespace(from_name=from_name)
    )
    monkeypatch.setitem(sys.modules, "modal", fake_modal)

    axiom_door1.main(
        [
            "--modal-environment",
            "main",
            "set",
            "--mode",
            "off",
            "--deny",
            "snap",
        ]
    )

    assert store["lookup"] == (
        "household-api-axiom-door1",
        {"create_if_missing": True, "environment_name": "main"},
    )
    assert fake_dict["control"]["mode"] == "off"
    assert fake_dict["control"]["deny"] == ["snap"]

    axiom_door1.main(["--modal-environment", "main", "clear"])

    assert "control" not in fake_dict
