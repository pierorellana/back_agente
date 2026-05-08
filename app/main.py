import logging
import time
from collections.abc import Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.exception_handlers import register_exception_handlers
from app.api.routers.care_estimates import router as care_estimates_router
from app.api.routers.insurance import router as insurance_router
from app.api.routers.notion import router as notion_router
from app.infrastructure.config.settings import Settings, get_settings


def configure_logging(settings: Settings) -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def parse_cors_origins(raw_origins: str) -> list[str]:
    if not raw_origins:
        return ["*"]
    origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
    return origins or ["*"]


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings)
    logger = logging.getLogger("app.http")

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
    )

    allowed_origins = parse_cors_origins(settings.cors_allowed_origins)
    allow_credentials = settings.cors_allow_credentials

    if allow_credentials and "*" in allowed_origins:
        logger.warning(
            "CORS_ALLOW_CREDENTIALS=true is incompatible with wildcard origins; "
            "disabling credentials."
        )
        allow_credentials = False

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def log_http_requests(
        request: Request,
        call_next: Callable[[Request], Response],
    ) -> Response:
        start = time.perf_counter()
        client = request.client.host if request.client else "-"
        logger.info(
            "request_started method=%s path=%s client=%s",
            request.method,
            request.url.path,
            client,
        )

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.exception(
                "request_failed method=%s path=%s duration_ms=%.2f",
                request.method,
                request.url.path,
                duration_ms,
            )
            raise

        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "request_finished method=%s path=%s status=%s duration_ms=%.2f",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response

    register_exception_handlers(app)
    app.include_router(notion_router, prefix=settings.api_prefix)
    app.include_router(insurance_router, prefix=settings.api_prefix)
    app.include_router(care_estimates_router, prefix=settings.api_prefix)

    return app


app = create_app()
