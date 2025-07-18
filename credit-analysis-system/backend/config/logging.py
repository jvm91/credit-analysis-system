"""
Конфигурация логирования
"""
import logging
import sys
from typing import Any, Dict

import structlog
from structlog.types import FilteringBoundLogger

from .settings import settings


def setup_logging() -> FilteringBoundLogger:
    """Настройка структурированного логирования"""

    # Конфигурация structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.TimeStamper(fmt="ISO"),
            structlog.processors.JSONRenderer() if settings.log_format == "json"
            else structlog.dev.ConsoleRenderer(colors=True)
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Настройка стандартного логгера Python
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level.upper()),
    )

    # Подавление избыточных логов
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    return structlog.get_logger()


def log_request_middleware(request_id: str, method: str, path: str) -> Dict[str, Any]:
    """Middleware для логирования запросов"""
    return {
        "request_id": request_id,
        "method": method,
        "path": path,
        "event": "request_started"
    }


def log_response_middleware(
        request_id: str,
        status_code: int,
        duration: float
) -> Dict[str, Any]:
    """Middleware для логирования ответов"""
    return {
        "request_id": request_id,
        "status_code": status_code,
        "duration_ms": round(duration * 1000, 2),
        "event": "request_completed"
    }


# Глобальный логгер
logger = setup_logging()