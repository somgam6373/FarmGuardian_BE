from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    # 가입 규칙(3~30자, 4~72자)보다 넉넉한 상한: 그보다 긴 값은 어떤 계정도 가질 수 없다
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=100)


class LoginOut(BaseModel):
    id: int
    username: str


class MeOut(BaseModel):
    id: int
    username: str
    onboarded: bool


class OnboardingOut(BaseModel):
    id: int
    onboarded: bool
