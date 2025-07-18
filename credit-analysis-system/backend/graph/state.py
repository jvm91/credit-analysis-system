"""
Определение состояния графа для LangGraph
"""
from datetime import datetime
from typing import TypedDict, List, Optional, Dict, Any
from enum import Enum


class ProcessingStatus(str, Enum):
    """Статусы обработки заявки"""
    STARTED = "started"
    VALIDATING = "validating"
    VALIDATION_COMPLETE = "validation_complete"
    LEGAL_CHECKING = "legal_checking"
    LEGAL_CHECK_COMPLETE = "legal_check_complete"
    RISK_ANALYZING = "risk_analyzing"
    RISK_ANALYSIS_COMPLETE = "risk_analysis_complete"
    RELEVANCE_CHECKING = "relevance_checking"
    RELEVANCE_CHECK_COMPLETE = "relevance_check_complete"
    FINANCIAL_ANALYZING = "financial_analyzing"
    FINANCIAL_ANALYSIS_COMPLETE = "financial_analysis_complete"
    DECISION_MAKING = "decision_making"
    COMPLETED = "completed"
    ERROR = "error"
    REJECTED = "rejected"


class AgentReasoning(TypedDict):
    """Структура рассуждений агента"""
    agent: str
    reasoning: str
    timestamp: str
    confidence: Optional[float]
    metadata: Optional[Dict[str, Any]]


class ValidationResult(TypedDict):
    """Результат валидации"""
    status: str
    score: float
    errors: List[str]
    warnings: List[str]
    extracted_data: Optional[Dict[str, Any]]


class AnalysisResult(TypedDict):
    """Базовая структура результата анализа"""
    status: str
    score: float
    confidence: float
    summary: str
    details: Dict[str, Any]
    recommendations: List[str]
    risks: List[str]


class FinalDecision(TypedDict):
    """Итоговое решение по заявке"""
    status: str  # approved, rejected, requires_review
    confidence: float
    amount_approved: Optional[float]
    conditions: List[str]
    reasoning: str
    risk_level: str
    expires_at: Optional[str]


class CreditApplicationState(TypedDict):
    """
    Основное состояние графа для обработки кредитной заявки
    """
    # Идентификация
    application_id: str
    created_at: str

    # Исходные данные заявки
    form_data: Dict[str, Any]
    pdf_files: List[str]

    # Результаты валидации
    validation_result: Optional[ValidationResult]
    validation_errors: List[str]

    # Результаты анализа агентов
    legal_analysis: Optional[AnalysisResult]
    risk_analysis: Optional[AnalysisResult]
    relevance_analysis: Optional[AnalysisResult]
    financial_analysis: Optional[AnalysisResult]

    # Рассуждения агентов (для отображения в UI)
    agent_reasoning: List[AgentReasoning]

    # Итоговое решение
    final_decision: Optional[FinalDecision]

    # Метаинформация о процессе
    current_step: ProcessingStatus
    errors: List[str]
    warnings: List[str]
    processing_start_time: str
    processing_end_time: Optional[str]
    total_processing_time: Optional[float]

    # Конфигурация обработки
    config: Optional[Dict[str, Any]]


def create_initial_state(
        application_id: str,
        form_data: Dict[str, Any],
        pdf_files: List[str],
        config: Optional[Dict[str, Any]] = None
) -> CreditApplicationState:
    """Создает начальное состояние для новой заявки"""

    now = datetime.now().isoformat()

    return CreditApplicationState(
        application_id=application_id,
        created_at=now,
        form_data=form_data,
        pdf_files=pdf_files,
        validation_result=None,
        validation_errors=[],
        legal_analysis=None,
        risk_analysis=None,
        relevance_analysis=None,
        financial_analysis=None,
        agent_reasoning=[],
        final_decision=None,
        current_step=ProcessingStatus.STARTED,
        errors=[],
        warnings=[],
        processing_start_time=now,
        processing_end_time=None,
        total_processing_time=None,
        config=config or {}
    )


def add_agent_reasoning(
        state: CreditApplicationState,
        agent_name: str,
        reasoning: str,
        confidence: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
) -> CreditApplicationState:
    """Добавляет рассуждение агента к состоянию"""

    new_reasoning = AgentReasoning(
        agent=agent_name,
        reasoning=reasoning,
        timestamp=datetime.now().isoformat(),
        confidence=confidence,
        metadata=metadata
    )

    return {
        **state,
        "agent_reasoning": state["agent_reasoning"] + [new_reasoning]
    }


def update_processing_step(
        state: CreditApplicationState,
        new_step: ProcessingStatus
) -> CreditApplicationState:
    """Обновляет текущий шаг обработки"""

    updated_state = {
        **state,
        "current_step": new_step
    }

    # Если процесс завершен, записываем время окончания
    if new_step in [ProcessingStatus.COMPLETED, ProcessingStatus.ERROR, ProcessingStatus.REJECTED]:
        end_time = datetime.now().isoformat()
        start_time = datetime.fromisoformat(state["processing_start_time"])
        end_time_dt = datetime.fromisoformat(end_time)
        processing_time = (end_time_dt - start_time).total_seconds()

        updated_state.update({
            "processing_end_time": end_time,
            "total_processing_time": processing_time
        })

    return updated_state


def add_error(
        state: CreditApplicationState,
        error: str
) -> CreditApplicationState:
    """Добавляет ошибку к состоянию"""

    return {
        **state,
        "errors": state["errors"] + [error]
    }


def add_warning(
        state: CreditApplicationState,
        warning: str
) -> CreditApplicationState:
    """Добавляет предупреждение к состоянию"""

    return {
        **state,
        "warnings": state["warnings"] + [warning]
    }