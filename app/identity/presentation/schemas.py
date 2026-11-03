from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field

from app.farm.presentation.schemas import Address, FarmmapId, FieldOut, Name, check_unique


class LoginIn(BaseModel):
    # 가입 규칙(3~30자, 4~72자)보다 넉넉한 상한: 그보다 긴 값은 어떤 계정도 가질 수 없다
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=100)


class SignupIn(BaseModel):
    username: str = Field(pattern=r"^[A-Za-z0-9_]{3,30}$")
    password: str = Field(min_length=4, max_length=72)
    field_name: Name
    parcel_farmmap_ids: Annotated[
        list[FarmmapId], Field(min_length=1, max_length=20), AfterValidator(check_unique)
    ]
    field_address: Address | None = None


class SignupOut(BaseModel):
    id: int
    username: str
    field: FieldOut


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
