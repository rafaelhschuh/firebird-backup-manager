from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.auth import create_session, delete_session, require_auth
from backend.database import verify_admin_password, set_admin_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    password: str


class TokenOut(BaseModel):
    token: str


class ChangePasswordBody(BaseModel):
    current_password: str
    new_password: str


@router.post("/login", response_model=TokenOut)
def login(body: LoginBody):
    if not verify_admin_password(body.password):
        raise HTTPException(status_code=401, detail="Senha incorreta")
    token = create_session()
    return TokenOut(token=token)


@router.post("/logout", status_code=204)
def logout(token: str = Depends(require_auth)):
    delete_session(token)
    return None


@router.get("/check")
def check(_token: str = Depends(require_auth)):
    return {"ok": True}


@router.put("/password", status_code=204)
def change_password(body: ChangePasswordBody, _token: str = Depends(require_auth)):
    if not verify_admin_password(body.current_password):
        raise HTTPException(status_code=400, detail="Senha atual incorreta")
    if len(body.new_password) < 4:
        raise HTTPException(status_code=400, detail="Nova senha muito curta (mínimo 4 caracteres)")
    set_admin_password(body.new_password)
    return None
