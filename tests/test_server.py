"""In-process startup smoke test for the supported FastAPI entrypoint."""


def test_canonical_application_starts_without_a_separate_server(client):
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json()["status"] == "alive"
