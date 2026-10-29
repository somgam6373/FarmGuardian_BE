from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import current_user
from app.core.db import get_db
from app.core.errors import AppError
from app.identity.application import service
from app.identity.presentation.schemas import LoginIn, LoginOut, MeOut, OnboardingOut

router = APIRouter()

UserId = Annotated[int, Depends(current_user)]


@router.post("/auth/login", response_model=LoginOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    found = service.login(db, body.username, body.password)
    if found is None:  # 아이디 없음·비밀번호 틀림을 구분하지 않는다
        raise AppError("UNAUTHORIZED", 401, "아이디 또는 비밀번호가 올바르지 않습니다")
    return LoginOut(id=found[0], username=found[1])


@router.get("/me", response_model=MeOut)
def read_me(user_id: UserId, db: Session = Depends(get_db)):
    me = service.get_me(db, user_id)
    return MeOut(id=me.id, username=me.username, onboarded=me.onboarded)


@router.post("/me/onboarding", response_model=OnboardingOut)
def complete_onboarding(user_id: UserId, db: Session = Depends(get_db)):
    service.complete_onboarding(db, user_id)
    return OnboardingOut(id=user_id, onboarded=True)


@router.delete("/me", status_code=204)
def withdraw(user_id: UserId, db: Session = Depends(get_db)):
    service.withdraw(db, user_id)
