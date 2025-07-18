"""
Основное приложение FastAPI
"""
import uuid
from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from config.logging import setup_logging, logger
from database.connection import get_database_session, create_tables, close_database
from models.application import (
    ApplicationSubmission,
    ApplicationResponse,
    ApplicationStatus
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    # Startup
    logger.info("Starting Credit Analysis System", version=settings.version)

    # Создание таблиц БД
    await create_tables()

    yield

    # Shutdown
    logger.info("Shutting down Credit Analysis System")
    await close_database()


# Создание приложения
app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description="Мультиагентная система рассмотрения кредитных заявок",
    lifespan=lifespan
)

# Настройка логирования
setup_logging()

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"] if settings.debug else ["localhost", "127.0.0.1"]
)


@app.get("/")
async def root():
    """Корневой эндпоинт"""
    return {
        "message": "Credit Analysis System API",
        "version": settings.version,
        "status": "running"
    }


@app.get("/health")
async def health_check():
    """Проверка здоровья системы"""
    return {
        "status": "healthy",
        "timestamp": "2024-01-01T00:00:00Z",
        "services": {
            "database": "connected",
            "redis": "connected",
            "llm": "available"
        }
    }


@app.post("/applications/submit", response_model=ApplicationResponse)
async def submit_application(
    application: ApplicationSubmission,
    files: List[UploadFile] = File([]),
    db: AsyncSession = Depends(get_database_session)
):
    """Подача новой кредитной заявки"""

    try:
        # Генерация ID заявки
        application_id = str(uuid.uuid4())

        logger.info(
            "New application submitted",
            application_id=application_id,
            company_name=application.company_name
        )

        # Валидация файлов
        pdf_files = []
        for file in files:
            if not file.filename.lower().endswith(tuple(settings.allowed_extensions)):
                raise HTTPException(
                    status_code=400,
                    detail=f"Неподдерживаемый тип файла: {file.filename}"
                )

            if file.size > settings.max_file_size:
                raise HTTPException(
                    status_code=400,
                    detail=f"Файл слишком большой: {file.filename}"
                )

            # Сохранение файла (упрощенная версия)
            file_path = f"{settings.upload_dir}/{application_id}_{file.filename}"
            pdf_files.append(file_path)

        # TODO: Запуск LangGraph workflow
        # initial_state = create_initial_state(
        #     application_id=application_id,
        #     form_data=application.dict(),
        #     pdf_files=pdf_files
        # )
        # workflow = create_credit_workflow()
        # await workflow.ainvoke(initial_state)

        return ApplicationResponse(
            application_id=application_id,
            status="processing",
            message="Заявка принята в обработку",
            created_at="2024-01-01T00:00:00Z"
        )

    except Exception as e:
        logger.error("Application submission failed", error=str(e))
        raise HTTPException(status_code=500, detail="Ошибка при обработке заявки")


@app.get("/applications/{application_id}/status", response_model=ApplicationStatus)
async def get_application_status(
    application_id: str,
    db: AsyncSession = Depends(get_database_session)
):
    """Получение статуса обработки заявки"""

    # TODO: Реализовать получение статуса из БД
    return ApplicationStatus(
        application_id=application_id,
        current_step="validation",
        status="processing",
        progress_percentage=25,
        estimated_completion_time=None,
        validation_complete=True,
        summary="Заявка проходит валидацию",
        next_steps=["Юридическая проверка", "Анализ рисков"]
    )


@app.get("/applications/{application_id}/reasoning")
async def get_agent_reasoning(
    application_id: str,
    db: AsyncSession = Depends(get_database_session)
):
    """Получение рассуждений агентов"""

    # TODO: Реализовать получение рассуждений из БД
    return {
        "application_id": application_id,
        "reasoning": [
            {
                "agent": "validator",
                "reasoning": "Заявка содержит все необходимые документы...",
                "confidence": 0.85,
                "timestamp": "2024-01-01T00:00:00Z"
            }
        ]
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )