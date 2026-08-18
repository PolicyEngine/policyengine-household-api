from __future__ import annotations

import argparse
import os
from typing import Any

import modal


CANARY_APP_NAME_ENV = "HOUSEHOLD_MODAL_CANARY_APP_NAME"
DEFAULT_CANARY_APP_NAME = "policyengine-household-api-canary"
CANARY_FUNCTION_NAME = "ping"


def verify_canary_app(
    app_name: str,
    *,
    modal_environment: str,
) -> dict[str, Any]:
    function = modal.Function.from_name(
        app_name,
        CANARY_FUNCTION_NAME,
        environment_name=modal_environment,
    )
    result = function.remote()
    if not isinstance(result, dict) or result.get("ok") is not True:
        raise RuntimeError(
            f"Canary app {app_name} returned an invalid ping response: "
            f"{result!r}"
        )

    print(
        f"Canary app {app_name} serves: ping returned {result!r}.",
        flush=True,
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify that a deployed Modal canary answers ping."
    )
    parser.add_argument(
        "--app-name",
        default=os.getenv(CANARY_APP_NAME_ENV, DEFAULT_CANARY_APP_NAME),
    )
    parser.add_argument("--modal-environment", required=True)
    args = parser.parse_args()
    verify_canary_app(
        args.app_name,
        modal_environment=args.modal_environment,
    )


if __name__ == "__main__":
    main()
