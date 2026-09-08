import json
import shutil
from typing import Literal
from uuid import UUID
from uuid import uuid4

from fastapi import APIRouter
from fastapi import Depends
from fastapi import File
from fastapi import Form
from fastapi import Query
from fastapi import Response
from fastapi import UploadFile
from sqlalchemy.orm import Session

from onyx.auth.permissions import require_permission
from onyx.db import meetings as db
from onyx.db.engine.sql_engine import get_session
from onyx.db.enums import Permission
from onyx.db.models import LocalMeeting
from onyx.db.models import User
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.meetings.config import enabled
from onyx.meetings.config import enqueue
from onyx.meetings.config import max_bytes
from onyx.meetings.config import storage_path
from onyx.meetings.models import MeetingSnapshot
from onyx.meetings.models import MeetingSummary
from shared_configs.contextvars import get_current_tenant_id


def require_enabled() -> None:
    if not enabled():
        raise OnyxError(OnyxErrorCode.ENV_VAR_GATED, "Meetings are disabled")


router = APIRouter(prefix="/meetings", dependencies=[Depends(require_enabled)])


@router.post("")
def upload(
    file: UploadFile = File(...),
    agenda: str = Form("", max_length=2000),
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    session: Session = Depends(get_session),
) -> MeetingSnapshot:
    meeting_id = uuid4()
    directory = storage_path(str(meeting_id))
    directory.mkdir(parents=True, mode=0o700)
    try:
        size = 0
        with (directory / "source").open("xb") as output:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes():
                    raise OnyxError(
                        OnyxErrorCode.INVALID_INPUT, "File exceeds upload limit"
                    )
                output.write(chunk)
        if size == 0:
            raise OnyxError(OnyxErrorCode.INVALID_INPUT, "Empty file")
        snapshot = db.create(
            session,
            LocalMeeting(
                id=meeting_id,
                user_id=user.id,
                filename=(file.filename or "recording")[:255],
                agenda=agenda,
                status="queued_transcribe",
                segments=[],
            ),
        )
    except Exception:
        shutil.rmtree(directory)
        raise
    finally:
        file.file.close()
    try:
        enqueue(str(meeting_id), get_current_tenant_id(), "transcribe")
    except Exception:
        db.update(
            meeting_id, status="failed", error="Queue unavailable; retry processing"
        )
        return db.read(meeting_id)
    return snapshot


@router.get("")
def list_meetings(
    offset: int = Query(0, ge=0),
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    session: Session = Depends(get_session),
) -> list[MeetingSummary]:
    return db.list_owned(session, user.id, offset)


@router.get("/{meeting_id}")
def get_meeting(
    meeting_id: UUID,
    q: str = Query("", max_length=1000),
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    session: Session = Depends(get_session),
) -> MeetingSnapshot:
    result = MeetingSnapshot.model_validate(db.owned(session, meeting_id, user.id))
    if q:
        result.segments = [
            segment
            for segment in result.segments
            if q.casefold() in segment.text.casefold()
        ]
    return result


@router.post("/{meeting_id}/retry")
def retry_meeting(
    meeting_id: UUID,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    session: Session = Depends(get_session),
) -> MeetingSnapshot:
    stage = db.prepare_retry(session, meeting_id, user.id)
    try:
        enqueue(str(meeting_id), get_current_tenant_id(), stage)
    except Exception:
        db.update(
            meeting_id, status="failed", error="Queue unavailable; retry processing"
        )
    return db.read(meeting_id)


@router.get("/{meeting_id}/export")
def export_meeting(
    meeting_id: UUID,
    format: Literal["txt", "json"] = "txt",
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    session: Session = Depends(get_session),
) -> Response:
    result = MeetingSnapshot.model_validate(db.owned(session, meeting_id, user.id))
    if format == "json":
        content = result.model_dump_json(indent=2)
    else:
        content = "\n".join(
            f"[{s.start:.2f}–{s.end:.2f}] {s.speaker}: {s.text}"
            for s in result.segments
        )
        if result.analysis:
            content += "\n\n" + json.dumps(
                result.analysis, ensure_ascii=False, indent=2
            )
    return Response(
        content,
        media_type="application/json" if format == "json" else "text/plain",
        headers={
            "Content-Disposition": f'attachment; filename="meeting-{meeting_id}.{format}"'
        },
    )
