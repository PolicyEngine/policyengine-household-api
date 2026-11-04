Let the staging Cloud Run gateway scale to zero between releases: the staging deploy job sets `HOUSEHOLD_CLOUD_RUN_GATEWAY_MIN_INSTANCES` to `0`. The production gateway keeps one instance.
