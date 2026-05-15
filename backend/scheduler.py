import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlmodel import Session, select

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone="UTC")


def _job_func(schedule_id: int) -> None:
    from backend.database import engine
    from backend.backup import run_backup
    from backend.restore import run_reindex
    from backend.models import Schedule, ScheduleConnection, Connection, ScheduleType

    with Session(engine) as session:
        schedule = session.get(Schedule, schedule_id)
        if not schedule or not schedule.enabled:
            return

        links = session.exec(
            select(ScheduleConnection).where(ScheduleConnection.schedule_id == schedule_id)
        ).all()

        for link in links:
            connection = session.get(Connection, link.connection_id)
            if connection and connection.enabled:
                try:
                    if schedule.schedule_type == ScheduleType.REINDEX:
                        run_reindex(connection, session)
                    else:
                        run_backup(connection, session)
                except Exception as exc:
                    logger.error("Erro no agendamento %s / %s: %s", schedule.name, connection.name, exc)


def load_schedules(session: Session) -> None:
    from backend.models import Schedule

    schedules = session.exec(select(Schedule).where(Schedule.enabled == True)).all()
    for sched in schedules:
        _register_job(sched)
    logger.info("%d agendamento(s) carregado(s).", len(schedules))


def _register_job(schedule) -> None:
    trigger = CronTrigger(
        hour=schedule.cron_hour,
        minute=schedule.cron_minute,
        day_of_week=schedule.days_of_week,
    )
    job_id = f"backup_{schedule.id}"
    scheduler.add_job(
        _job_func,
        trigger=trigger,
        id=job_id,
        args=[schedule.id],
        replace_existing=True,
        misfire_grace_time=300,
    )
    logger.debug("Job registrado: %s (%s)", job_id, schedule.name)


def add_or_update_job(schedule) -> None:
    _register_job(schedule)


def remove_job(schedule_id: int) -> None:
    job_id = f"backup_{schedule_id}"
    try:
        scheduler.remove_job(job_id)
    except Exception:
        pass


def get_next_run(schedule_id: int):
    job = scheduler.get_job(f"backup_{schedule_id}")
    if job and job.next_run_time:
        return job.next_run_time.isoformat()
    return None
