def test_liveness_check(deployed_api):
    response = deployed_api.get("/liveness_check")

    assert response.status_code == 200
    assert response.text == "OK"


def test_readiness_check(deployed_api):
    response = deployed_api.get("/readiness_check")

    assert response.status_code == 200
    assert response.text == "OK"
