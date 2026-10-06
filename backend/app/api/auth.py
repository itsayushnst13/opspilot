from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.db import get_db
from ..core.security import create_token, get_current_user, verify_password
from ..models import User
from .deps import login_limit

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: str
    password: str


@router.post("/login", dependencies=[Depends(login_limit)])
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")
    return {"access_token": create_token(user.email, user.role), "token_type": "bearer",
            "user": {"email": user.email, "name": user.display_name, "role": user.role}}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"email": user.email, "name": user.display_name, "role": user.role}


@router.get("/demo-users")
def demo_users(db: Session = Depends(get_db)):
    """Lists demo accounts for the login screen. Disabled when ENV=prod and a custom demo password is not intended."""
    s = get_settings()
    if s.env == "prod" and not s.expose_demo_users:
        return {"enabled": False, "users": []}
    users = db.scalars(select(User).order_by(User.id)).all()
    return {"enabled": True, "password": s.demo_password,
            "users": [{"email": u.email, "name": u.display_name, "role": u.role} for u in users]}
