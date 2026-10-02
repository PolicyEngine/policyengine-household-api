PRODUCTION_WORKER_RESOURCE_OPTIONS = {
    "current": {
        "min_containers": 3,
        "buffer_containers": 2,
        "scaledown_window": 600,
    },
    "frontier": {
        "min_containers": 1,
        "buffer_containers": 1,
        "scaledown_window": 300,
    },
}
