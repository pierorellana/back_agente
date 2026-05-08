from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.application.dtos.responses.general_response import ErrorDTO, GeneralResponse
from app.domain.errors import BusinessRuleError, IntegrationError, NotFoundError


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    payload = GeneralResponse(
        success=False,
        error=ErrorDTO(code=code, message=message),
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump())


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(BusinessRuleError)
    async def business_rule_error_handler(
        request: Request,
        exc: BusinessRuleError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_400_BAD_REQUEST,
            "BUSINESS_RULE_ERROR",
            str(exc),
        )

    @app.exception_handler(NotFoundError)
    async def not_found_error_handler(request: Request, exc: NotFoundError) -> JSONResponse:
        return _error_response(
            status.HTTP_404_NOT_FOUND,
            "NOT_FOUND",
            str(exc),
        )

    @app.exception_handler(IntegrationError)
    async def integration_error_handler(request: Request, exc: IntegrationError) -> JSONResponse:
        return _error_response(
            status.HTTP_502_BAD_GATEWAY,
            "INTEGRATION_ERROR",
            str(exc),
        )
