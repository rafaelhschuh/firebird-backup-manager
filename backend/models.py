from datetime import datetime
from enum import Enum
from typing import Optional
from sqlmodel import Field, SQLModel


class BackupStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    RUNNING = "RUNNING"


class Connection(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    host: str
    port: int = 3050
    db_path: str
    username: str
    password: str  # Fernet-encrypted
    backup_path: str
    retention_count: int = 7
    gbak_path: Optional[str] = None
    enabled: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Schedule(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    cron_hour: int
    cron_minute: int
    days_of_week: str = "0,1,2,3,4,5,6"  # 0=seg, 6=dom
    enabled: bool = True


class ScheduleConnection(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    schedule_id: int = Field(foreign_key="schedule.id")
    connection_id: int = Field(foreign_key="connection.id")


class BackupLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    connection_id: int = Field(foreign_key="connection.id")
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None
    status: BackupStatus = BackupStatus.RUNNING
    fbk_path: Optional[str] = None
    fbk_size_bytes: Optional[int] = None
    duration_seconds: Optional[float] = None
    error_message: Optional[str] = None
    gbak_output: Optional[str] = None  # saída completa do gbak


class AppConfig(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    app_port: int = 8099
    app_secret_key: str = ""
    admin_password_hash: str = ""
    admin_password_salt: str = ""
    logo_filename: Optional[str] = None
