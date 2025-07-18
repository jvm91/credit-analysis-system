"""
Основное приложение FastAPI с полной интеграцией LangGraph
"""
import uuid
import os
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
import aiofiles

from config.settings import settings
from config.logging import setup_logging, logger
from database.connection import get_database_session, create_tables, close_database
from models.application import (
    ApplicationSubmission,
    ApplicationResponse,
    ApplicationStatus,
    AgentReasoningResponse
)
from graph.workflow import process_credit_application, get_application_state
from graph.state import create_initial_state


class ConnectionManager:
    """Менеджер WebSocket соединений"""

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, application_id: str):
        await websocket.accept()
        self.active_connections[application_id] = websocket
        logger.info("WebSocket connected", application_id=application_id)

    def disconnect(self, application_id: str):
        if application_id in self.active_connections:
            del self.active_connections[application_id]
            logger.info("WebSocket disconnected", application_id=application_id)

    async def send_update(self, application_id: str, message: dict):
        """Отправка обновления конкретному приложению"""
        if application_id in self.active_connections:
            try:
                await self.active_connections[application_id].send_json(message)
            except Exception as e:
                logger.error("Failed to send WebSocket update",
                           application_id=application_id, error=str(e))
                self.disconnect(application_id)


manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    # Startup
    logger.info("Starting Credit Analysis System", version=settings.version)

    # Создание директорий
    os.makedirs(settings.upload_dir, exist_ok=True)

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
        "status": "running",
        "endpoints": {
            "submit": "/applications/submit",
            "status": "/applications/{id}/status",
            "reasoning": "/applications/{id}/reasoning",
            "websocket": "/ws/applications/{id}"
        }
    }


@app.get("/health")
async def health_check():
    """Проверка здоровья системы"""

    # Проверяем доступность компонентов
    health_status = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "services": {}
    }

    # Проверка базы данных
    try:
        # Простой запрос к БД
        health_status["services"]["database"] = "connected"
    except Exception as e:
        health_status["services"]["database"] = f"error: {str(e)}"
        health_status["status"] = "unhealthy"

    # Проверка LLM сервиса
    try:
        from services.llm_service import llm_service
        model_info = llm_service.get_model_info()
        health_status["services"]["llm"] = f"available ({model_info['model']})"
    except Exception as e:
        health_status["services"]["llm"] = f"error: {str(e)}"
        health_status["status"] = "degraded"

    # Проверка директории загрузок
    if os.path.exists(settings.upload_dir):
        health_status["services"]["file_storage"] = "available"
    else:
        health_status["services"]["file_storage"] = "unavailable"

    return health_status


@app.post("/applications/submit", response_model=ApplicationResponse)
async def submit_application(
    application: ApplicationSubmission,
    files: List[UploadFile] = File([]),
    db: AsyncSession = Depends(get_database_session)
):
    """Подача новой кредитной заявки с запуском LangGraph обработки"""

    try:
        # Генерация ID заявки
        application_id = str(uuid.uuid4())

        logger.info(
            "New application submitted",
            application_id=application_id,
            company_name=application.company_name,
            requested_amount=application.requested_amount,
            files_count=len(files)
        )

        # Валидация и сохранение файлов
        pdf_files = []
        for file in files:
            # Проверка типа файла
            if not file.filename.lower().endswith(tuple(settings.allowed_extensions)):
                raise HTTPException(
                    status_code=400,
                    detail=f"Неподдерживаемый тип файла: {file.filename}"
                )

            # Проверка размера файла
            content = await file.read()
            if len(content) > settings.max_file_size:
                raise HTTPException(
                    status_code=400,
                    detail=f"Файл слишком большой: {file.filename}"
                )

            # Сохранение файла
            file_path = os.path.join(settings.upload_dir, f"{application_id}_{file.filename}")
            async with aiofiles.open(file_path, 'wb') as f:
                await f.write(content)

            pdf_files.append(file_path)
            logger.info("File saved", file_path=file_path, size=len(content))

        # Запуск LangGraph обработки в фоновом режиме
        import asyncio

        async def process_application_background():
            """Фоновая обработка заявки через LangGraph"""
            try:
                logger.info("Starting background processing", application_id=application_id)

                # Запускаем обработку через LangGraph workflow
                final_state = await process_credit_application(
                    application_id=application_id,
                    form_data=application.dict(),
                    pdf_files=pdf_files
                )

                # Отправляем финальное обновление через WebSocket
                await manager.send_update(application_id, {
                    "type": "final_decision",
                    "status": final_state["current_step"],
                    "decision": final_state.get("final_decision"),
                    "timestamp": datetime.now().isoformat()
                })

                logger.info("Background processing completed",
                          application_id=application_id,
                          final_status=final_state["current_step"])

            except Exception as e:
                logger.error("Background processing failed",
                           application_id=application_id, error=str(e))

                # Отправляем ошибку через WebSocket
                await manager.send_update(application_id, {
                    "type": "error",
                    "message": f"Ошибка обработки: {str(e)}",
                    "timestamp": datetime.now().isoformat()
                })

        # Запускаем обработку в фоне
        asyncio.create_task(process_application_background())

        return ApplicationResponse(
            application_id=application_id,
            status="processing",
            message="Заявка принята в обработку. Подключитесь к WebSocket для отслеживания прогресса.",
            created_at=datetime.now()
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Application submission failed", error=str(e))
        raise HTTPException(status_code=500, detail="Ошибка при обработке заявки")


@app.get("/applications/{application_id}/status", response_model=ApplicationStatus)
async def get_application_status(
    application_id: str,
    db: AsyncSession = Depends(get_database_session)
):
    """Получение текущего статуса обработки заявки"""

    try:
        # Получаем состояние из LangGraph
        state = await get_application_state(application_id)

        if not state:
            raise HTTPException(status_code=404, detail="Заявка не найдена")

        # Определяем прогресс на основе текущего шага
        progress_map = {
            "started": 5,
            "validating": 15,
            "validation_complete": 20,
            "legal_checking": 30,
            "legal_check_complete": 40,
            "risk_analyzing": 50,
            "risk_analysis_complete": 60,
            "relevance_checking": 70,
            "relevance_check_complete": 80,
            "financial_analyzing": 85,
            "financial_analysis_complete": 90,
            "decision_making": 95,
            "completed": 100,
            "error": 0,
            "rejected": 100
        }

        current_step = state.get("current_step", "started")
        progress_percentage = progress_map.get(current_step, 0)

        # Определяем следующие шаги
        next_steps = []
        if current_step == "validation_complete":
            next_steps = ["Юридическая проверка", "Анализ рисков"]
        elif current_step == "legal_check_complete":
            next_steps = ["Анализ рисков", "Проверка актуальности"]
        elif current_step == "risk_analysis_complete":
            next_steps = ["Проверка актуальности", "Финансовый анализ"]
        elif current_step == "relevance_check_complete":
            next_steps = ["Финансовый анализ", "Принятие решения"]
        elif current_step == "financial_analysis_complete":
            next_steps = ["Принятие итогового решения"]

        # Создаем краткую сводку
        summary = f"Заявка находится на этапе: {current_step}"
        if state.get("final_decision"):
            decision = state["final_decision"]
            summary = f"Решение: {decision.get('status', 'неизвестно')}"

        return ApplicationStatus(
            application_id=application_id,
            current_step=current_step,
            status="processing" if progress_percentage < 100 else "completed",
            progress_percentage=progress_percentage,
            estimated_completion_time=None,
            validation_complete=progress_percentage >= 20,
            legal_check_complete=progress_percentage >= 40,
            risk_analysis_complete=progress_percentage >= 60,
            relevance_check_complete=progress_percentage >= 80,
            financial_analysis_complete=progress_percentage >= 90,
            summary=summary,
            next_steps=next_steps
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get application status",
                    application_id=application_id, error=str(e))
        raise HTTPException(status_code=500, detail="Ошибка получения статуса")


@app.get("/applications/{application_id}/reasoning")
async def get_agent_reasoning(
    application_id: str,
    db: AsyncSession = Depends(get_database_session)
):
    """Получение рассуждений агентов"""

    try:
        # Получаем состояние из LangGraph
        state = await get_application_state(application_id)

        if not state:
            raise HTTPException(status_code=404, detail="Заявка не найдена")

        # Преобразуем рассуждения в нужный формат
        reasoning_list = []
        agent_reasoning = state.get("agent_reasoning", [])

        for reasoning in agent_reasoning:
            reasoning_list.append(AgentReasoningResponse(
                agent=reasoning["agent"],
                reasoning=reasoning["reasoning"],
                confidence=reasoning.get("confidence"),
                timestamp=datetime.fromisoformat(reasoning["timestamp"]),
                metadata=reasoning.get("metadata")
            ))

        return {
            "application_id": application_id,
            "reasoning": reasoning_list,
            "total_agents": len(reasoning_list),
            "last_update": reasoning_list[-1].timestamp if reasoning_list else None
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get agent reasoning",
                    application_id=application_id, error=str(e))
        raise HTTPException(status_code=500, detail="Ошибка получения рассуждений")


@app.websocket("/ws/applications/{application_id}")
async def websocket_endpoint(websocket: WebSocket, application_id: str):
    """WebSocket для отслеживания прогресса обработки заявки в real-time"""

    await manager.connect(websocket, application_id)

    try:
        # Отправляем начальное состояние
        try:
            state = await get_application_state(application_id)
            if state:
                await websocket.send_json({
                    "type": "initial_state",
                    "current_step": state.get("current_step", "unknown"),
                    "agent_reasoning": state.get("agent_reasoning", []),
                    "timestamp": datetime.now().isoformat()
                })
        except Exception as e:
            logger.warning("Failed to send initial state", error=str(e))

        # Поддерживаем соединение
        while True:
            try:
                # Ждем сообщения от клиента (пинг для поддержания соединения)
                data = await websocket.receive_text()

                if data == "ping":
                    await websocket.send_json({
                        "type": "pong",
                        "timestamp": datetime.now().isoformat()
                    })

            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error("WebSocket error", application_id=application_id, error=str(e))
                break

    finally:
        manager.disconnect(application_id)


@app.get("/applications/{application_id}/download/{file_name}")
async def download_file(application_id: str, file_name: str):
    """Скачивание загруженных файлов"""

    # Проверяем безопасность пути
    safe_filename = os.path.basename(file_name)
    expected_prefix = f"{application_id}_"

    if not safe_filename.startswith(expected_prefix):
        raise HTTPException(status_code=403, detail="Доступ запрещен")

    file_path = os.path.join(settings.upload_dir, safe_filename)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Файл не найден")

    from fastapi.responses import FileResponse
    return FileResponse(
        path=file_path,
        filename=safe_filename,
        media_type='application/octet-stream'
    )


# Дополнительные административные эндпоинты

@app.get("/admin/applications")
async def list_applications(
    limit: int = 10,
    offset: int = 0,
    db: AsyncSession = Depends(get_database_session)
):
    """Список всех заявок (для администрирования)"""

    # TODO: Реализовать запрос к БД
    return {
        "applications": [],
        "total": 0,
        "limit": limit,
        "offset": offset
    }


@app.delete("/applications/{application_id}")
async def delete_application(
    application_id: str,
    db: AsyncSession = Depends(get_database_session)
):
    """Удаление заявки и связанных файлов"""

    try:
        # Удаляем файлы
        import glob
        file_pattern = os.path.join(settings.upload_dir, f"{application_id}_*")
        files_to_delete = glob.glob(file_pattern)

        for file_path in files_to_delete:
            try:
                os.remove(file_path)
                logger.info("File deleted", file_path=file_path)
            except Exception as e:
                logger.warning("Failed to delete file", file_path=file_path, error=str(e))

        # TODO: Удаление из БД

        return {"message": "Заявка удалена", "files_deleted": len(files_to_delete)}

    except Exception as e:
        logger.error("Failed to delete application",
                    application_id=application_id, error=str(e))
        raise HTTPException(status_code=500, detail="Ошибка удаления заявки")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )