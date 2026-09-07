from datetime import datetime
from datetime import timedelta
from datetime import timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from onyx.db.engine.sql_engine import get_session_with_current_tenant
from onyx.db.models import LocalMeeting
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.meetings.models import MeetingSnapshot


def owned(session: Session, meeting_id: UUID, owner_id: UUID) -> LocalMeeting:
    meeting = session.scalar(
        select(LocalMeeting).where(
            LocalMeeting.id == meeting_id, LocalMeeting.user_id == owner_id
        )
    )
    if meeting is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Meeting not found")
    return meeting


def create(session: Session, meeting: LocalMeeting) -> MeetingSnapshot:
    session.add(meeting)
    session.commit()
    session.refresh(meeting)
    return MeetingSnapshot.model_validate(meeting)


def list_owned(session: Session, owner_id: UUID, offset: int) -> list[MeetingSnapshot]:
    rows = session.scalars(
        select(LocalMeeting)
        .where(LocalMeeting.user_id == owner_id)
        .order_by(LocalMeeting.created_at.desc())
        .offset(offset)
        .limit(50)
    )
    return [MeetingSnapshot.model_validate(row) for row in rows]


def update(meeting_id: UUID, **values: object) -> None:
    with get_session_with_current_tenant() as session:
        row = session.get(LocalMeeting, meeting_id)
        if row is None:
            raise ValueError("Meeting not found")
        for key, value in values.items():
            setattr(row, key, value)
        row.updated_at = datetime.now(timezone.utc)
        session.commit()


def read(meeting_id: UUID) -> MeetingSnapshot:
    with get_session_with_current_tenant() as session:
        row = session.get(LocalMeeting, meeting_id)
        if row is None:
            raise ValueError("Meeting not found")
        return MeetingSnapshot.model_validate(row)


def prepare_retry(session: Session, meeting_id: UUID, owner_id: UUID) -> str:
    row = session.scalar(
        select(LocalMeeting)
        .where(LocalMeeting.id == meeting_id, LocalMeeting.user_id == owner_id)
        .with_for_update()
    )
    if row is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND)
    stale = row.updated_at < datetime.now(timezone.utc) - timedelta(hours=25)
    if row.status not in ("failed", "completed") and not stale:
        raise OnyxError(OnyxErrorCode.CONFLICT, "Meeting is still processing")
    stage = "analyze" if row.status == "completed" else "transcribe"
    row.status = f"queued_{stage}"
    row.error = None
    row.updated_at = datetime.now(timezone.utc)
    session.commit()
    return stage
