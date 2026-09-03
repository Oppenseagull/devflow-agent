import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import TaskStatus


class RepositoryPayload(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)


class PullRequestPayload(BaseModel):
    number: int = Field(gt=0)


class GitHubWebhookPayload(BaseModel):
    repository: RepositoryPayload
    pull_request: PullRequestPayload


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    repository: str
    pr_number: int
    status: TaskStatus
    created_at: datetime
    updated_at: datetime


class HealthResponse(BaseModel):
    status: str
    database: str


class ErrorResponse(BaseModel):
    detail: str

