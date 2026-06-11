"""Unit tests for plan_docker_tags.py"""

import pytest

from plan_docker_tags import (
    PlanError,
    _next_page_url,
    build_plan,
    read_pyproject_versions,
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


class TestNextPageUrl:
    def test_parses_next_link(self):
        header = '</v2/x/tags/list?n=1000&last=foo>; rel="next"'
        assert (
            _next_page_url(header)
            == "https://ghcr.io/v2/x/tags/list?n=1000&last=foo"
        )

    def test_no_next_link(self):
        assert _next_page_url("") is None
