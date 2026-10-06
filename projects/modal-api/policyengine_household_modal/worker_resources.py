from collections.abc import Mapping
from typing import Final, TypedDict

from policyengine_household_common.release_manifest import (
    WorkerResourceProfile,
)


class WorkerAutoscalerOptions(TypedDict):
    min_containers: int
    buffer_containers: int
    scaledown_window: int


PRODUCTION_WORKER_RESOURCE_OPTIONS: Final[
    Mapping[WorkerResourceProfile, WorkerAutoscalerOptions]
] = {
    WorkerResourceProfile.CURRENT: {
        "min_containers": 3,
        "buffer_containers": 2,
        "scaledown_window": 600,
    },
    WorkerResourceProfile.FRONTIER: {
        "min_containers": 1,
        "buffer_containers": 1,
        "scaledown_window": 300,
    },
}
