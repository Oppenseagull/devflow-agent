import logging
import uuid

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Task
from app.schemas import ErrorResponse, GitHubWebhookPayload, HealthResponse, TaskRead
from app.service import create_task_from_webhook

settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name, version="0.1.0")


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
    responses={503: {"model": ErrorResponse}},
)
def github_webhook(
    payload: GitHubWebhookPayload,
    db: Session = Depends(get_db),
) -> Task:
    try:
        return create_task_from_webhook(db, payload)
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
