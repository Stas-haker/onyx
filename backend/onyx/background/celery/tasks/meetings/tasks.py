import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID

from celery import shared_task

from onyx.db import meetings as db
from onyx.meetings.config import enabled
from onyx.meetings.config import enqueue
from onyx.meetings.config import STAGES
from onyx.meetings.config import storage_path
from onyx.redis.redis_pool import get_redis_client


@shared_task(name="onyx.meetings.process", ignore_result=True)
def process(meeting_id: str, tenant_id: str, stage: str) -> None:
    if not enabled() or stage not in STAGES:
        return
    identifier = UUID(meeting_id)
    timeout = int(os.environ.get("MEETINGS_STAGE_TIMEOUT", "21600"))
    redis = get_redis_client(tenant_id=tenant_id)
    # Duplicated deliveries cannot launch competing GPU subprocesses for a file.
    lock = redis.lock(f"meeting:{identifier}", timeout=timeout + 120, blocking=False)
    if not lock.acquire():
        return
    directory = storage_path(meeting_id)
    next_stage: str | None = None
    try:
        snapshot = db.read(identifier)
        if snapshot.status != f"queued_{stage}":
            return
        db.update(identifier, status=stage, error=None)
        (directory / "input.json").write_text(
            snapshot.model_dump_json(), encoding="utf-8"
        )
        (directory / "result.json").unlink(missing_ok=True)
        script = (
            Path(__file__).resolve().parents[5] / "scripts" / "process_local_meeting.py"
        )
        subprocess.run(
            [
                os.environ.get("MEETINGS_PYTHON", sys.executable),
                str(script),
                str(directory),
                stage,
            ],
            timeout=timeout,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        result = json.loads((directory / "result.json").read_text(encoding="utf-8"))
        index = STAGES.index(stage)
        next_stage = STAGES[index + 1] if index + 1 < len(STAGES) else None
        db.update(
            identifier,
            **result,
            status=f"queued_{next_stage}" if next_stage else "completed",
        )
    except Exception:
        next_stage = None
        # Never persist exception strings: decoders/HTTP libraries may include
        # sensitive transcript content, prompts or internal credentials.
        db.update(
            identifier,
            status="failed",
            error=f"Stage {stage} failed; check local models, GPU memory and service availability, then retry",
        )
    finally:
        for name in ("input.json", "result.json", "result.tmp"):
            (directory / name).unlink(missing_ok=True)
        lock.release()
    # Publish after releasing the lock so a fast next worker cannot discard it.
    if next_stage:
        try:
            enqueue(meeting_id, tenant_id, next_stage)
        except Exception:
            db.update(
                identifier, status="failed", error="Queue unavailable; retry processing"
            )
