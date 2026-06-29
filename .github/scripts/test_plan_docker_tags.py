"""Unit tests for plan_docker_tags.py"""

import urllib.error

import pytest

from plan_docker_tags import (
    PlanError,
    _next_page_url,
    build_plan,
    fetch_existing_tags,
    parse_bool_flag,
    plan_live_retags,
    read_pyproject_versions,
    should_sync_channels,
)


WEEKLY_CHANNELS = {"current": "1.715.2", "frontier": "1.726.0"}


class TestReleasePlan:
    def test_release_builds_exact_api_and_sha_tags(self):
        plan = build_plan(
            mode="release",
            pinned_us_version="1.726.0",
            api_version="0.21.4",
            head_sha="ec6b957a83826b274664c944f6a72f6f2b479d16",
            channel_versions=WEEKLY_CHANNELS,
            existing_tags={"us-1.715.2"},
        )
        release_build = plan["builds"][0]
        assert release_build["us_version"] == "1.726.0"
        assert release_build["tags"].split() == [
            "us-1.726.0",
            "0.21.4",
            "sha-ec6b957a83826b274664c944f6a72f6f2b479d16",
        ]

    def test_release_retags_channels_without_rebuilding_current(self):
        plan = build_plan(
            mode="release",
            pinned_us_version="1.726.0",
            api_version="0.21.4",
            head_sha="abc123",
            channel_versions=WEEKLY_CHANNELS,
            existing_tags={"us-1.715.2"},
        )
        assert len(plan["builds"]) == 1
        assert plan["retags"] == [
            {"source": "us-1.715.2", "targets": ["current", "latest"]},
            {"source": "us-1.726.0", "targets": ["frontier"]},
        ]

    def test_release_backfills_missing_current_image(self):
        plan = build_plan(
            mode="release",
            pinned_us_version="1.726.0",
            api_version="0.21.4",
            head_sha="abc123",
            channel_versions=WEEKLY_CHANNELS,
            existing_tags=set(),
        )
        backfill = [b for b in plan["builds"] if b["us_version"] == "1.715.2"]
        assert backfill == [{"us_version": "1.715.2", "tags": "us-1.715.2"}]

    def test_release_does_not_backfill_the_release_version(self):
        plan = build_plan(
            mode="release",
            pinned_us_version="1.726.0",
            api_version="0.21.4",
            head_sha="abc123",
            channel_versions={"current": "1.726.0", "frontier": "1.726.0"},
            existing_tags=set(),
        )
        assert len(plan["builds"]) == 1
        assert plan["retags"] == [
            {
                "source": "us-1.726.0",
                "targets": ["current", "latest", "frontier"],
            }
        ]

    def test_release_requires_versions_and_sha(self):
        with pytest.raises(PlanError):
            build_plan(mode="release", pinned_us_version="1.726.0")

    def test_release_rejects_missing_channel(self):
        with pytest.raises(PlanError):
            build_plan(
                mode="release",
                pinned_us_version="1.726.0",
                api_version="0.21.4",
                head_sha="abc123",
                channel_versions={"current": "1.715.2", "frontier": ""},
            )


class TestDispatchPlan:
    def test_dispatch_builds_requested_version_only(self):
        plan = build_plan(
            mode="dispatch",
            requested_us_version="1.725.0",
        )
        assert plan["builds"] == [
            {"us_version": "1.725.0", "tags": "us-1.725.0"}
        ]
        assert plan["retags"] == []

    def test_dispatch_sync_only_repoints_existing_images(self):
        plan = build_plan(
            mode="dispatch",
            channel_versions=WEEKLY_CHANNELS,
            existing_tags={"us-1.715.2", "us-1.726.0"},
        )
        assert plan["builds"] == []
        assert len(plan["retags"]) == 2

    def test_dispatch_sync_backfills_both_missing_channels(self):
        plan = build_plan(
            mode="dispatch",
            channel_versions=WEEKLY_CHANNELS,
            existing_tags=set(),
        )
        assert {b["us_version"] for b in plan["builds"]} == {
            "1.715.2",
            "1.726.0",
        }

    def test_dispatch_with_no_inputs_fails(self):
        with pytest.raises(PlanError):
            build_plan(mode="dispatch")

    def test_dispatch_rejects_malformed_version(self):
        with pytest.raises(PlanError):
            build_plan(mode="dispatch", requested_us_version="1.725.0; rm -rf")


class TestReadPyprojectVersions:
    def test_extracts_pin_and_project_version(self, tmp_path):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[project]\nname = "x"\nversion = "0.21.4"\n'
            'dependencies = ["flask>=2", "policyengine_us==1.726.0"]\n'
        )
        assert read_pyproject_versions(pyproject) == ("1.726.0", "0.21.4")

    def test_accepts_hyphenated_pin_spelling(self, tmp_path):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[project]\nname = "x"\nversion = "0.21.4"\n'
            'dependencies = ["policyengine-us==1.726.0"]\n'
        )
        assert read_pyproject_versions(pyproject) == ("1.726.0", "0.21.4")

    def test_missing_exact_pin_raises(self, tmp_path):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[project]\nname = "x"\nversion = "0.21.4"\n'
            'dependencies = ["policyengine_us>=1.0"]\n'
        )
        with pytest.raises(PlanError):
            read_pyproject_versions(pyproject)


class TestVersionValidation:
    """The only thing guarding values that flow into build-args and tags."""

    def test_release_rejects_malformed_pin(self):
        with pytest.raises(PlanError):
            build_plan(
                mode="release",
                pinned_us_version="1.0; rm -rf /",
                api_version="0.21.4",
                head_sha="abc123",
                channel_versions=WEEKLY_CHANNELS,
                existing_tags={"us-1.715.2"},
            )

    def test_rejects_malformed_channel_version(self):
        with pytest.raises(PlanError):
            build_plan(
                mode="dispatch",
                channel_versions={
                    "current": "1.0; rm -rf",
                    "frontier": "1.726.0",
                },
                existing_tags=set(),
            )

    def test_rejects_missing_channel_key(self):
        # The gateway omits a channel whose app reference is unset.
        with pytest.raises(PlanError):
            build_plan(
                mode="dispatch",
                channel_versions={"current": "1.744.0"},
                existing_tags=set(),
            )


class TestChannelCollapse:
    def test_dispatch_sync_collapsed_channel_backfills_once(self):
        # current == frontier on a version that is neither planned nor
        # already published: exactly one build and one 3-target retag.
        plan = build_plan(
            mode="dispatch",
            channel_versions={"current": "1.726.0", "frontier": "1.726.0"},
            existing_tags=set(),
        )
        assert plan["builds"] == [
            {"us_version": "1.726.0", "tags": "us-1.726.0"}
        ]
        assert plan["retags"] == [
            {
                "source": "us-1.726.0",
                "targets": ["current", "latest", "frontier"],
            }
        ]


class TestPlanLiveRetags:
    def test_retags_only_published_images(self):
        retags, skipped = plan_live_retags(
            channel_versions=WEEKLY_CHANNELS,
            existing_tags={"us-1.715.2", "us-1.726.0"},
        )
        assert retags == [
            {"source": "us-1.715.2", "targets": ["current", "latest"]},
            {"source": "us-1.726.0", "targets": ["frontier"]},
        ]
        assert skipped == []

    def test_skips_channel_whose_image_is_not_built_yet(self):
        # A release completed mid-build and moved frontier ahead; that image
        # is not published yet, so frontier must not be repointed.
        retags, skipped = plan_live_retags(
            channel_versions={"current": "1.726.0", "frontier": "1.744.0"},
            existing_tags={"us-1.726.0"},
        )
        assert retags == [
            {"source": "us-1.726.0", "targets": ["current", "latest"]}
        ]
        assert skipped == [{"version": "1.744.0", "targets": ["frontier"]}]

    def test_collapsed_channels_single_retag(self):
        retags, skipped = plan_live_retags(
            channel_versions={"current": "1.726.0", "frontier": "1.726.0"},
            existing_tags={"us-1.726.0"},
        )
        assert retags == [
            {
                "source": "us-1.726.0",
                "targets": ["current", "latest", "frontier"],
            }
        ]
        assert skipped == []

    def test_missing_channel_raises(self):
        with pytest.raises(PlanError):
            plan_live_retags(
                channel_versions={"current": "1.726.0"},
                existing_tags=set(),
            )


class TestSyncGate:
    def test_release_always_syncs(self):
        assert should_sync_channels("release", False) is True
        assert should_sync_channels("release", True) is True

    def test_dispatch_syncs_only_when_flagged(self):
        assert should_sync_channels("dispatch", False) is False
        assert should_sync_channels("dispatch", True) is True


class TestParseBoolFlag:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("true", True),
            ("True", True),
            ("TRUE", True),
            ("false", False),
            ("", False),
            ("yes", False),
        ],
    )
    def test_parses_workflow_boolean(self, value, expected):
        assert parse_bool_flag(value) is expected


class TestFetchExistingTags:
    def test_treats_404_as_empty(self, monkeypatch):
        """A never-pushed/deleted package returns no tags rather than crash."""

        class _TokenResponse:
            def read(self):
                return b'{"token": "anon"}'

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def fake_urlopen(target, timeout=None):
            if isinstance(target, str):  # anonymous token request
                return _TokenResponse()
            raise urllib.error.HTTPError(  # tags/list for a fresh package
                target.full_url, 404, "Not Found", {}, None
            )

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        assert fetch_existing_tags("policyengine/x") == set()


class TestNextPageUrl:
    def test_parses_next_link(self):
        header = '</v2/x/tags/list?n=1000&last=foo>; rel="next"'
        assert (
            _next_page_url(header)
            == "https://ghcr.io/v2/x/tags/list?n=1000&last=foo"
        )

    def test_no_next_link(self):
        assert _next_page_url("") is None
