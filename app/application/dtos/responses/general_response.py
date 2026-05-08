from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ErrorDTO(BaseModel):
    code: str
    message: str
    details: dict | None = None


class GeneralResponse(BaseModel, Generic[T]):
    success: bool
    message: str | None = None
    data: T | None = None
    error: ErrorDTO | None = None
