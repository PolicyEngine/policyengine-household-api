from __future__ import annotations

import argparse
import sys

import modal
from modal.exception import NotFoundError

from policyengine_household_common.release_manifest import (
    MANIFEST_DICT_KEY,
    MANIFEST_DICT_NAME,
    require_active_current_and_frontier,
)


def main() -> int:
    args = _parse_args()
    try:
        manifest_dict = modal.Dict.from_name(
            MANIFEST_DICT_NAME,
            create_if_missing=False,
            environment_name=args.modal_environment,
        )
    except NotFoundError:
        print(
            "Modal release manifest is missing; both `current` and "
            "`frontier` must be configured before deploying.",
            file=sys.stderr,
        )
        return 1

    try:
        require_active_current_and_frontier(
            manifest_dict.get(MANIFEST_DICT_KEY)
        )
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1

    print("Modal release manifest has active `current` and `frontier` apps.")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fail unless the Modal release manifest has both active channels."
        )
    )
    parser.add_argument("--modal-environment", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
