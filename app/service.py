import logging

from sqlalchemy.orm import Session

from app.models import Task, TaskStatus
from app.schemas import GitHubWebhookPayload

logger = logging.getLogger(__name__)


def create_task_from_webhook(db: Session, payload: GitHubWebhookPayload) -> Task:
    task = Task(
        repository=payload.repository.full_name,
        pr_number=payload.pull_request.number,
        status=TaskStatus.RECEIVED.value,
    )
    db.add(task)
    db.flush()
    logger.info("Task %s received for %s#%s", task.id, task.repository, task.pr_number)

    task.status = TaskStatus.PROCESSING.value
    db.flush()
    logger.info("Task %s is processing", task.id)

    task.status = TaskStatus.COMPLETED.value
    db.commit()
    db.refresh(task)
    logger.info("Task %s completed", task.id)
    return task

