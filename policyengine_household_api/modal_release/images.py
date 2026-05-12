from __future__ import annotations

import modal
import os


def household_api_image() -> modal.Image:
    return (
        modal.Image.debian_slim(python_version="3.12")
        .uv_sync(".", frozen=True)
        .add_local_python_source("policyengine_household_api", copy=True)
        .add_local_dir("config", remote_path="/app/config", copy=True)
    )


def household_api_secret() -> modal.Secret:
    return modal.Secret.from_name(
        os.getenv("HOUSEHOLD_MODAL_SECRET_NAME", "household-api")
    )
