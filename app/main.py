import logging
import uuid

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.github import verify_github_signature
from app.models import Task
from app.schemas import (
    ErrorResponse,
    GitHubWebhookPayload,
    HealthResponse,
    TaskRead,
    WebhookIgnoredResponse,
)
from app.service import create_task_from_webhook

settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name, version="0.2.0")

SUPPORTED_PULL_REQUEST_ACTIONS = {"opened", "synchronize", "reopened"}


@app.exception_handler(SQLAlchemyError)
async def database_exception_handler(_request, exc: SQLAlchemyError) -> JSONResponse:
    logger.exception("Database operation failed", exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "Database is unavailable"},
    )


@app.get(
    "/health",
    response_model=HealthResponse,
    responses={503: {"model": ErrorResponse}},
)
def health(db: Session = Depends(get_db)) -> HealthResponse:
    db.execute(text("SELECT 1"))
    return HealthResponse(status="ok", database="reachable")


@app.post(
    "/webhooks/github",
    response_model=TaskRead,
    status_code=status.HTTP_201_CREATED,
    responses={
        202: {"model": WebhookIgnoredResponse},
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
async def github_webhook(
    request: Request,
    db: Session = Depends(get_db),
) -> Task | JSONResponse:
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")

    if not settings.github_webhook_secret:
        logger.error("GITHUB_WEBHOOK_SECRET is not configured")
        raise HTTPException(status_code=503, detail="Webhook secret is not configured")
    if signature is None:
        raise HTTPException(status_code=403, detail="Missing GitHub webhook signature")
    if not verify_github_signature(body, signature, settings.github_webhook_secret):
        raise HTTPException(status_code=403, detail="Invalid GitHub webhook signature")

    event = request.headers.get("X-GitHub-Event")
    delivery_id = request.headers.get("X-GitHub-Delivery")
    if event is None or delivery_id is None:
        raise HTTPException(status_code=400, detail="Missing GitHub webhook headers")

    if event != "pull_request":
        logger.info("Ignored GitHub delivery=%s event=%s", delivery_id, event)
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"status": "ignored", "reason": "Unsupported GitHub event"},
        )

    try:
        payload = GitHubWebhookPayload.model_validate_json(body)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="Invalid pull_request payload") from exc

    if payload.action not in SUPPORTED_PULL_REQUEST_ACTIONS:
        logger.info(
            "Ignored GitHub delivery=%s event=%s action=%s",
            delivery_id,
            event,
            payload.action,
        )
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"status": "ignored", "reason": "Unsupported pull_request action"},
        )

    try:
        return create_task_from_webhook(
            db,
            payload,
            delivery_id=delivery_id,
            event=event,
        )
    except SQLAlchemyError:
        db.rollback()
        raise


@app.get(
    "/tasks/{task_id}",
    response_model=TaskRead,
    responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
def get_task(task_id: uuid.UUID, db: Session = Depends(get_db)) -> Task:
    task = db.scalar(select(Task).where(Task.id == task_id))
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.get(
    "/tasks",
    response_model=list[TaskRead],
    responses={503: {"model": ErrorResponse}},
)
def list_tasks(db: Session = Depends(get_db)) -> list[Task]:
    query = select(Task).order_by(Task.created_at.desc()).limit(20)
    tasks = db.scalars(query).all()
    return tasks
