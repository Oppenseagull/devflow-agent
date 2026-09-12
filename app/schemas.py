import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import TaskStatus


class RepositoryPayload(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)


class PullRequestPayload(BaseModel):
    number: int = Field(gt=0)


class GitHubWebhookPayload(BaseModel):
    action: str = Field(min_length=1, max_length=50)
    repository: RepositoryPayload
    pull_request: PullRequestPayload


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    repository: str
    pr_number: int
    status: TaskStatus
    github_delivery_id: str | None
    github_event: str | None
    github_action: str | None
    created_at: datetime
    updated_at: datetime


class WebhookIgnoredResponse(BaseModel):
    status: Literal["ignored"]
    reason: str


class HealthResponse(BaseModel):
    status: str
    database: str


class ErrorResponse(BaseModel):
    detail: str
