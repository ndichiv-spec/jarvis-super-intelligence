"""Media endpoints must not claim unsupported video work succeeded."""

from io import BytesIO


def test_video_capabilities_require_authentication(client):
    assert client.post("/api/v1/video/analyze").status_code == 401
    assert client.post("/api/v1/video/extract-frames").status_code == 401
    assert client.post("/api/v1/video/info").status_code == 401


def test_video_capabilities_report_unavailable_without_claiming_success(client, auth_headers):
    upload = {"file": ("clip.mp4", BytesIO(b"video bytes"), "video/mp4")}

    for path in (
        "/api/v1/video/analyze",
        "/api/v1/video/extract-frames",
        "/api/v1/video/info",
    ):
        response = client.post(path, headers=auth_headers, files=upload)
        assert response.status_code == 501
        assert response.json()["error"]["code"] == "CAPABILITY_NOT_CONFIGURED"
