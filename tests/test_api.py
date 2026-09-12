import hashlib
import hmac
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.conftest import TEST_WEBHOOK_SECRET


def pull_request_payload(action: str = "opened", pr_number: int = 42) -> dict:
    return {
        "action": action,
        "repository": {
            "full_name": "octocat/devflow",
            "html_url": "https://github.com/octocat/devflow",
        },
        "pull_request": {
            "number": pr_number,
            "title": "A real payload contains fields V1 does not need",
        },
        "sender": {"login": "octocat"},
    }


def signed_webhook_headers(
    body: bytes,
    *,
    event: str = "pull_request",
    delivery_id: str | None = None,
    secret: str = TEST_WEBHOOK_SECRET,
) -> dict[str, str]:
    signature = "sha256=" + hmac.new(
        secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    return {
        "Content-Type": "application/json",
        "X-Hub-Signature-256": signature,
        "X-GitHub-Event": event,
        "X-GitHub-Delivery": delivery_id or str(uuid.uuid4()),
    }


def post_signed_webhook(
    client: TestClient,
    payload: dict,
    *,
    event: str = "pull_request",
    delivery_id: str | None = None,
):
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    return client.post(
        "/webhooks/github",
        content=body,
        headers=signed_webhook_headers(
            body, event=event, delivery_id=delivery_id
        ),
    )


def test_health_returns_database_status(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "reachable"}


@pytest.mark.parametrize("action", ["opened", "synchronize", "reopened"])
def test_valid_signature_creates_task_for_supported_actions(
    client: TestClient, action: str
) -> None:
    response = post_signed_webhook(client, pull_request_payload(action=action))

    assert response.status_code == 201
    body = response.json()
    uuid.UUID(body["id"])
    assert body["repository"] == "octocat/devflow"
    assert body["pr_number"] == 42
    assert body["status"] == "COMPLETED"
    assert body["github_event"] == "pull_request"
    assert body["github_action"] == action
    assert body["created_at"]
    assert body["updated_at"]


def test_wrong_signature_is_rejected(client: TestClient) -> None:
    payload = pull_request_payload()
    body = json.dumps(payload).encode("utf-8")
    headers = signed_webhook_headers(body, secret="the-wrong-secret")

    response = client.post("/webhooks/github", content=body, headers=headers)

    assert response.status_code == 403
    assert response.json() == {"detail": "Invalid GitHub webhook signature"}


def test_missing_signature_is_rejected(client: TestClient) -> None:
    body = json.dumps(pull_request_payload()).encode("utf-8")
    headers = signed_webhook_headers(body)
    headers.pop("X-Hub-Signature-256")

    response = client.post("/webhooks/github", content=body, headers=headers)

    assert response.status_code == 403
    assert response.json() == {"detail": "Missing GitHub webhook signature"}


def test_delivery_event_and_action_are_saved(client: TestClient) -> None:
    delivery_id = "72d3162e-cc78-11e3-81ab-4c9367dc0958"

    created = post_signed_webhook(
        client,
        pull_request_payload(action="synchronize", pr_number=7),
        delivery_id=delivery_id,
    ).json()
    fetched = client.get(f"/tasks/{created['id']}")

    assert fetched.status_code == 200
    assert fetched.json()["github_delivery_id"] == delivery_id
    assert fetched.json()["github_event"] == "pull_request"
    assert fetched.json()["github_action"] == "synchronize"


def test_non_pull_request_event_is_ignored(client: TestClient) -> None:
    response = post_signed_webhook(
        client,
        {"zen": "Keep it logically awesome."},
        event="ping",
    )

    assert response.status_code == 202
    assert response.json() == {
        "status": "ignored",
        "reason": "Unsupported GitHub event",
    }
    assert client.get("/tasks").json() == []


def test_unsupported_pull_request_action_is_ignored(client: TestClient) -> None:
    response = post_signed_webhook(client, pull_request_payload(action="closed"))

    assert response.status_code == 202
    assert response.json()["status"] == "ignored"
    assert client.get("/tasks").json() == []


def test_created_task_can_still_be_fetched(client: TestClient) -> None:
    created = post_signed_webhook(
        client, pull_request_payload(pr_number=7)
    ).json()

    response = client.get(f"/tasks/{created['id']}")

    assert response.status_code == 200
    assert response.json() == created


def test_missing_task_returns_404(client: TestClient) -> None:
    response = client.get(f"/tasks/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Task not found"}


def test_invalid_webhook_returns_422(client: TestClient) -> None:
    response = post_signed_webhook(
        client,
        {
            "action": "opened",
            "repository": {"full_name": ""},
            "pull_request": {"number": 0},
        },
    )

    assert response.status_code == 422


def test_list_tasks_returns_empty_list(client: TestClient) -> None:
    response = client.get("/tasks")

    assert response.status_code == 200
    assert response.json() == []


def test_list_tasks_returns_created_task(client: TestClient) -> None:
    post_signed_webhook(client, pull_request_payload())

    response = client.get("/tasks")

    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert len(response.json()) == 1


def test_list_tasks_returns_at_most_20(client: TestClient) -> None:
    for number in range(25):
        post_signed_webhook(client, pull_request_payload(pr_number=number + 1))

    response = client.get("/tasks")

    assert response.status_code == 200
    assert len(response.json()) == 20


def test_list_tasks_is_ordered_by_created_at(client: TestClient) -> None:
    for number in range(3):
        payload = pull_request_payload(pr_number=number + 1)
        payload["repository"]["full_name"] = f"octocat/repo-{number}"
        post_signed_webhook(client, payload)

    response = client.get("/tasks")
    tasks = response.json()

    assert response.status_code == 200
    assert len(tasks) == 3
    created_times = [task["created_at"] for task in tasks]
    assert created_times == sorted(created_times, reverse=True)
