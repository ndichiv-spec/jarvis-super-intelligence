from __future__ import annotations

from io import BytesIO

from jarvis_backend.core import create_token, get_store
from jarvis_backend.routers import multimodal


def _headers_for(user_id: str) -> dict[str, str]:
    get_store("users").save_key(
        user_id,
        {
            "id": user_id,
            "email": f"{user_id}@example.test",
            "roles": ["user"],
            "is_active": True,
        },
    )
    return {"Authorization": f"Bearer {create_token({'sub': user_id})}"}


def test_workspace_owner_is_server_derived_and_cross_user_mutation_denied(client):
    owner = _headers_for("workspace-owner")
    other = _headers_for("workspace-other")

    response = client.post(
        "/api/v1/browser/workspaces",
        json={
            "name": "Private workspace",
            "permissions": {"user_id": "workspace-other"},
        },
        headers=owner,
    )
    assert response.status_code == 422

    response = client.post(
        "/api/v1/browser/workspaces",
        json={"name": "Private workspace"},
        headers=owner,
    )
    assert response.status_code == 200
    workspace = response.json()["workspace"]
    workspace_id = workspace["id"]
    assert workspace["owner_id"] == "workspace-owner"

    assert client.get("/api/v1/browser/workspaces", headers=other).json()["count"] == 0
    assert client.put(
        f"/api/v1/browser/workspaces/{workspace_id}",
        json={"name": "stolen"},
        headers=other,
    ).status_code == 404
    assert client.post(
        f"/api/v1/browser/workspaces/{workspace_id}/associate",
        json={"type": "evidence", "id": "foreign-evidence"},
        headers=other,
    ).status_code == 404


def test_workspace_cannot_associate_another_users_session(client):
    owner = _headers_for("workspace-owner")
    _headers_for("workspace-other")
    created = client.post(
        "/api/v1/browser/workspaces",
        json={"name": "Private workspace"},
        headers=owner,
    )
    workspace_id = created.json()["workspace"]["id"]
    sessions = get_store("browser_sessions").load()
    sessions["foreign-session"] = {
        "id": "foreign-session",
        "user_id": "workspace-other",
    }
    get_store("browser_sessions").save()

    response = client.post(
        f"/api/v1/browser/workspaces/{workspace_id}/associate",
        json={"type": "session", "id": "foreign-session"},
        headers=owner,
    )
    assert response.status_code == 404


def test_multimodal_uploads_are_authenticated_and_private(client, tmp_path, monkeypatch):
    monkeypatch.setattr(multimodal, "UPLOADS_DIR", tmp_path)
    owner = _headers_for("upload-owner")
    other = _headers_for("upload-other")
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16

    assert client.get("/api/v1/multimodal/files").status_code == 401
    uploaded = client.post(
        "/api/v1/multimodal/upload/image",
        files={"file": ("pixel.png", BytesIO(png), "image/png")},
        headers=owner,
    )
    assert uploaded.status_code == 200
    metadata = uploaded.json()
    assert "path" not in metadata
    assert metadata["original_name"] == "pixel.png"

    listed = client.get("/api/v1/multimodal/files", headers=other)
    assert listed.status_code == 200
    assert listed.json() == {"files": [], "total": 0}
    assert client.delete(
        f"/api/v1/multimodal/files/{metadata['id']}",
        headers=other,
    ).status_code == 404
    assert (tmp_path / "images" / metadata["filename"]).exists()


def test_multimodal_upload_rejects_mismatched_content_and_oversized_file(
    client, tmp_path, monkeypatch
):
    monkeypatch.setattr(multimodal, "UPLOADS_DIR", tmp_path)
    headers = _headers_for("upload-owner")

    invalid = client.post(
        "/api/v1/multimodal/upload/image",
        files={"file": ("fake.png", BytesIO(b"not an image"), "image/png")},
        headers=headers,
    )
    assert invalid.status_code == 415

    oversized = client.post(
        "/api/v1/multimodal/upload/document",
        files={
            "file": (
                "large.txt",
                BytesIO(b"x" * (multimodal.MAX_UPLOAD_BYTES + 1)),
                "text/plain",
            )
        },
        headers=headers,
    )
    assert oversized.status_code == 413
    assert list(tmp_path.rglob("*")) == []
