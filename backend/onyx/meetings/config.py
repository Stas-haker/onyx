import os
from pathlib import Path


def enabled() -> bool:
    return os.environ.get("MEETINGS_ENABLED", "false").lower() == "true"


def storage_path(meeting_id: str) -> Path:
    from uuid import UUID

    root = Path(os.environ.get("MEETINGS_STORAGE_PATH", "/var/lib/onyx/meetings"))
    return root / str(UUID(meeting_id))


def max_bytes() -> int:
    return int(os.environ.get("MEETINGS_MAX_UPLOAD_BYTES", str(2 * 1024**3)))


TASK_EXPIRES = 86400
STAGES = ("transcribe", "diarize", "analyze")


def enqueue(meeting_id: str, tenant_id: str, stage: str) -> None:
    from onyx.background.celery.versioned_apps.client import app

    if stage not in STAGES:
        raise ValueError("Invalid meeting stage")
    app.send_task(
        "onyx.meetings.process",
        kwargs={"meeting_id": meeting_id, "tenant_id": tenant_id, "stage": stage},
        queue=f"meetings_{stage}",
        expires=TASK_EXPIRES,
    )
