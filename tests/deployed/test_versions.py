def test_requested_version_matches_staging_channel(
    deployed_api,
    expected_channel,
    request_version,
    route_mode,
):
    if not expected_channel or not route_mode:
        return

    response = deployed_api.get("/versions/us")

    assert response.status_code == 200
    versions = response.json()
    expected_package_version = versions.get(expected_channel)
    assert expected_package_version

    if route_mode == "channel":
        assert request_version == expected_channel
    elif route_mode == "exact":
        assert request_version == expected_package_version
    else:
        raise AssertionError(f"Unexpected route mode: {route_mode}")
