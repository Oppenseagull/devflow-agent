import uuid

from fastapi.testclient import TestClient


def test_health_returns_database_status(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "reachable"}


def test_webhook_creates_completed_task(client: TestClient) -> None:
    response = client.post(
        "/webhooks/github",
        json={
            "repository": {"full_name": "octocat/devflow"},
            "pull_request": {"number": 42},
        },
    )

    assert response.status_code == 201
    body = response.json()
    uuid.UUID(body["id"])
    assert body["repository"] == "octocat/devflow"
    assert body["pr_number"] == 42
    assert body["status"] == "COMPLETED"
    assert body["created_at"]
    assert body["updated_at"]


def test_created_task_can_be_fetched(client: TestClient) -> None:
    created = client.post(
        "/webhooks/github",
        json={
            "repository": {"full_name": "octocat/devflow"},
            "pull_request": {"number": 7},
        },
    ).json()

    response = client.get(f"/tasks/{created['id']}")

    assert response.status_code == 200
    assert response.json() == created


def test_missing_task_returns_404(client: TestClient) -> None:
    response = client.get(f"/tasks/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Task not found"}


def test_invalid_webhook_returns_422(client: TestClient) -> None:
    response = client.post(
        "/webhooks/github",
        json={
            "repository": {"full_name": ""},
            "pull_request": {"number": 0},
        },
    )

    assert response.status_code == 422

