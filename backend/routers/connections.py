from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from backend.auth import require_auth
from backend.backup import encrypt_password
from backend.database import get_session
from backend.models import Connection
from backend.scheduler import remove_job

router = APIRouter(prefix="/api/connections", tags=["connections"], dependencies=[Depends(require_auth)])


class ConnectionCreate(BaseModel):
    name: str
    host: str
    port: int = 3050
    db_path: str
    username: str
    password: str
    backup_path: str
    retention_count: int = 7
    gbak_path: Optional[str] = None
    enabled: bool = True


class ConnectionUpdate(BaseModel):
    name: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    db_path: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    backup_path: Optional[str] = None
    retention_count: Optional[int] = None
    gbak_path: Optional[str] = None
    enabled: Optional[bool] = None


class ConnectionOut(BaseModel):
    id: int
    name: str
    host: str
    port: int
    db_path: str
    username: str
    backup_path: str
    retention_count: int
    gbak_path: Optional[str]
    enabled: bool

    model_config = {"from_attributes": True}


@router.get("", response_model=list[ConnectionOut])
def list_connections(session: Session = Depends(get_session)):
    return session.exec(select(Connection)).all()


@router.post("", response_model=ConnectionOut, status_code=201)
def create_connection(body: ConnectionCreate, session: Session = Depends(get_session)):
    conn = Connection(
        **body.model_dump(exclude={"password"}),
        password=encrypt_password(body.password),
    )
    session.add(conn)
    session.commit()
    session.refresh(conn)
    return conn


@router.put("/{conn_id}", response_model=ConnectionOut)
def update_connection(conn_id: int, body: ConnectionUpdate, session: Session = Depends(get_session)):
    conn = session.get(Connection, conn_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Conexão não encontrada")

    data = body.model_dump(exclude_none=True)
    if "password" in data:
        data["password"] = encrypt_password(data["password"])

    for k, v in data.items():
        setattr(conn, k, v)

    session.add(conn)
    session.commit()
    session.refresh(conn)
    return conn


@router.delete("/{conn_id}", status_code=204)
def delete_connection(conn_id: int, session: Session = Depends(get_session)):
    conn = session.get(Connection, conn_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Conexão não encontrada")

    from backend.models import ScheduleConnection
    links = session.exec(select(ScheduleConnection).where(ScheduleConnection.connection_id == conn_id)).all()
    for link in links:
        session.delete(link)

    session.delete(conn)
    session.commit()
