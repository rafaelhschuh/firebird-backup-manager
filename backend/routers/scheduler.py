from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from backend.auth import require_auth
from backend.database import get_session
from backend.models import Schedule, ScheduleConnection, Connection, ScheduleType
from backend import scheduler as sched_module

router = APIRouter(prefix="/api/schedules", tags=["schedules"], dependencies=[Depends(require_auth)])


class ScheduleCreate(BaseModel):
    name: str
    cron_hour: int
    cron_minute: int
    days_of_week: str = "0,1,2,3,4,5,6"
    enabled: bool = True
    schedule_type: ScheduleType = ScheduleType.BACKUP
    connection_ids: list[int] = []


class ScheduleUpdate(BaseModel):
    name: Optional[str] = None
    cron_hour: Optional[int] = None
    cron_minute: Optional[int] = None
    days_of_week: Optional[str] = None
    enabled: Optional[bool] = None
    schedule_type: Optional[ScheduleType] = None
    connection_ids: Optional[list[int]] = None


class ScheduleOut(BaseModel):
    id: int
    name: str
    cron_hour: int
    cron_minute: int
    days_of_week: str
    enabled: bool
    schedule_type: ScheduleType = ScheduleType.BACKUP
    next_run: Optional[str] = None
    connection_ids: list[int] = []

    model_config = {"from_attributes": True}


def _get_connection_ids(schedule_id: int, session: Session) -> list[int]:
    links = session.exec(
        select(ScheduleConnection).where(ScheduleConnection.schedule_id == schedule_id)
    ).all()
    return [l.connection_id for l in links]


def _enrich(sched: Schedule, session: Session) -> dict:
    return {
        "id": sched.id,
        "name": sched.name,
        "cron_hour": sched.cron_hour,
        "cron_minute": sched.cron_minute,
        "days_of_week": sched.days_of_week,
        "enabled": sched.enabled,
        "schedule_type": sched.schedule_type,
        "next_run": sched_module.get_next_run(sched.id),
        "connection_ids": _get_connection_ids(sched.id, session),
    }


def _sync_connections(schedule_id: int, connection_ids: list[int], session: Session) -> None:
    existing = session.exec(
        select(ScheduleConnection).where(ScheduleConnection.schedule_id == schedule_id)
    ).all()
    for link in existing:
        session.delete(link)
    for cid in connection_ids:
        session.add(ScheduleConnection(schedule_id=schedule_id, connection_id=cid))
    session.commit()


@router.get("", response_model=list[ScheduleOut])
def list_schedules(session: Session = Depends(get_session)):
    scheds = session.exec(select(Schedule)).all()
    return [_enrich(s, session) for s in scheds]


@router.post("", response_model=ScheduleOut, status_code=201)
def create_schedule(body: ScheduleCreate, session: Session = Depends(get_session)):
    sched = Schedule(
        name=body.name,
        cron_hour=body.cron_hour,
        cron_minute=body.cron_minute,
        days_of_week=body.days_of_week,
        enabled=body.enabled,
        schedule_type=body.schedule_type,
    )
    session.add(sched)
    session.commit()
    session.refresh(sched)

    _sync_connections(sched.id, body.connection_ids, session)

    if sched.enabled:
        sched_module.add_or_update_job(sched)

    return _enrich(sched, session)


@router.put("/{sched_id}", response_model=ScheduleOut)
def update_schedule(sched_id: int, body: ScheduleUpdate, session: Session = Depends(get_session)):
    sched = session.get(Schedule, sched_id)
    if not sched:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado")

    data = body.model_dump(exclude_none=True, exclude={"connection_ids"})
    for k, v in data.items():
        setattr(sched, k, v)
    session.add(sched)
    session.commit()
    session.refresh(sched)

    if body.connection_ids is not None:
        _sync_connections(sched.id, body.connection_ids, session)

    if sched.enabled:
        sched_module.add_or_update_job(sched)
    else:
        sched_module.remove_job(sched.id)

    return _enrich(sched, session)


@router.delete("/{sched_id}", status_code=204)
def delete_schedule(sched_id: int, session: Session = Depends(get_session)):
    sched = session.get(Schedule, sched_id)
    if not sched:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado")

    existing = session.exec(
        select(ScheduleConnection).where(ScheduleConnection.schedule_id == sched_id)
    ).all()
    for link in existing:
        session.delete(link)

    sched_module.remove_job(sched.id)
    session.delete(sched)
    session.commit()
