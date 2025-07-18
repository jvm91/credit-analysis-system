"""
Основной LangGraph workflow для обработки кредитных заявок
"""
from typing import Literal
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresCheckpointer

from .state import CreditApplicationState, ProcessingStatus
from .nodes.validator_node import validator_node
from .nodes.legal_node import legal_node
from .nodes.risk_node import risk_node
from .nodes.relevance_node import relevance_node
from .nodes.financial_node import financial_node
from .nodes.decision_node import decision_node
from .edges.routing import (
    should_continue_after_validation,
    should_continue_after_legal,
    should_continue_after_risk,
    should_continue_after_relevance,
    should_continue_after_financial
)
from ..config.settings import settings
from ..config.logging import logger


def create_credit_workflow():
    """Создание основного workflow для обработки кредитных заявок"""

    # Создаем граф с типизированным состоянием
    workflow = StateGraph(CreditApplicationState)

    # Добавляем узлы (агентов)
    workflow.add_node("validator", validator_node)
    workflow.add_node("legal_checker", legal_node)
    workflow.add_node("risk_manager", risk_node)
    workflow.add_node("relevance_checker", relevance_node)
    workflow.add_node("financial_analyzer", financial_node)
    workflow.add_node("decision_maker", decision_node)

    # Устанавливаем точку входа
    workflow.set_entry_point("validator")

    # Добавляем условные переходы
    workflow.add_conditional_edges(
        "validator",
        should_continue_after_validation,
        {
            "continue": "legal_checker",
            "reject": "decision_maker",
            "error": END
        }
    )

    workflow.add_conditional_edges(
        "legal_checker",
        should_continue_after_legal,
        {
            "continue": "risk_manager",
            "reject": "decision_maker",
            "error": END
        }
    )

    workflow.add_conditional_edges(
        "risk_manager",
        should_continue_after_risk,
        {
            "continue": "relevance_checker",
            "reject": "decision_maker",
            "error": END
        }
    )

    workflow.add_conditional_edges(
        "relevance_checker",
        should_continue_after_relevance,
        {
            "continue": "financial_analyzer",
            "reject": "decision_maker",
            "error": END
        }
    )

    workflow.add_conditional_edges(
        "financial_analyzer",
        should_continue_after_financial,
        {
            "continue": "decision_maker",
            "reject": "decision_maker",
            "error": END
        }
    )

    # Финальный узел всегда завершает процесс
    workflow.add_edge("decision_maker", END)

    logger.info("Credit workflow graph created successfully")
    return workflow


def create_workflow_with_checkpointing():
    """Создание workflow с поддержкой checkpointing"""

    # Создаем базовый workflow
    workflow = create_credit_workflow()

    # Настраиваем PostgreSQL checkpointer
    checkpointer = PostgresCheckpointer.from_conn_string(
        settings.database_url,
        schema="credit_analysis"
    )

    # Компилируем граф с checkpointer
    compiled_workflow = workflow.compile(
        checkpointer=checkpointer,
        interrupt_before=[],  # Можно добавить узлы для прерывания
        interrupt_after=[]  # Можно добавить узлы для прерывания после выполнения
    )

    logger.info("Workflow compiled with PostgreSQL checkpointing")
    return compiled_workflow


def get_workflow_visualization():
    """Получение визуализации графа для frontend"""

    workflow = create_credit_workflow()

    # Создаем структуру для frontend визуализации
    nodes = [
        {
            "id": "validator",
            "label": "Валидация",
            "type": "process",
            "position": {"x": 100, "y": 100},
            "data": {
                "description": "Валидация заявки и документов",
                "agent": "validator"
            }
        },
        {
            "id": "legal_checker",
            "label": "Юридическая проверка",
            "type": "process",
            "position": {"x": 300, "y": 100},
            "data": {
                "description": "Проверка юридической чистоты",
                "agent": "legal"
            }
        },
        {
            "id": "risk_manager",
            "label": "Анализ рисков",
            "type": "process",
            "position": {"x": 500, "y": 100},
            "data": {
                "description": "Оценка рисков проекта",
                "agent": "risk"
            }
        },
        {
            "id": "relevance_checker",
            "label": "Актуальность",
            "type": "process",
            "position": {"x": 700, "y": 100},
            "data": {
                "description": "Проверка актуальности проекта",
                "agent": "relevance"
            }
        },
        {
            "id": "financial_analyzer",
            "label": "Финансовый анализ",
            "type": "process",
            "position": {"x": 900, "y": 100},
            "data": {
                "description": "Анализ финансовой устойчивости",
                "agent": "financial"
            }
        },
        {
            "id": "decision_maker",
            "label": "Принятие решения",
            "type": "decision",
            "position": {"x": 500, "y": 300},
            "data": {
                "description": "Формирование итогового решения",
                "agent": "decision"
            }
        }
    ]

    edges = [
        {
            "id": "validator-legal",
            "source": "validator",
            "target": "legal_checker",
            "type": "conditional",
            "label": "Одобрено"
        },
        {
            "id": "legal-risk",
            "source": "legal_checker",
            "target": "risk_manager",
            "type": "conditional",
            "label": "Одобрено"
        },
        {
            "id": "risk-relevance",
            "source": "risk_manager",
            "target": "relevance_checker",
            "type": "conditional",
            "label": "Одобрено"
        },
        {
            "id": "relevance-financial",
            "source": "relevance_checker",
            "target": "financial_analyzer",
            "type": "conditional",
            "label": "Одобрено"
        },
        {
            "id": "financial-decision",
            "source": "financial_analyzer",
            "target": "decision_maker",
            "type": "default",
            "label": "Анализ завершен"
        },
        # Пути отклонения
        {
            "id": "validator-decision-reject",
            "source": "validator",
            "target": "decision_maker",
            "type": "conditional",
            "label": "Отклонено",
            "style": {"stroke": "red"}
        },
        {
            "id": "legal-decision-reject",
            "source": "legal_checker",
            "target": "decision_maker",
            "type": "conditional",
            "label": "Отклонено",
            "style": {"stroke": "red"}
        },
        {
            "id": "risk-decision-reject",
            "source": "risk_manager",
            "target": "decision_maker",
            "type": "conditional",
            "label": "Отклонено",
            "style": {"stroke": "red"}
        },
        {
            "id": "relevance-decision-reject",
            "source": "relevance_checker",
            "target": "decision_maker",
            "type": "conditional",
            "label": "Отклонено",
            "style": {"stroke": "red"}
        }
    ]

    return {
        "nodes": nodes,
        "edges": edges,
        "layout": "horizontal"
    }


# Глобальный экземпляр workflow
credit_workflow = None


def get_credit_workflow():
    """Получение глобального экземпляра workflow"""
    global credit_workflow

    if credit_workflow is None:
        credit_workflow = create_workflow_with_checkpointing()
        logger.info("Global credit workflow initialized")

    return credit_workflow


async def process_credit_application(
        application_id: str,
        form_data: dict,
        pdf_files: list,
        config: dict = None
) -> dict:
    """
    Основная функция для обработки кредитной заявки через LangGraph
    """
    from .state import create_initial_state

    # Создаем начальное состояние
    initial_state = create_initial_state(
        application_id=application_id,
        form_data=form_data,
        pdf_files=pdf_files,
        config=config
    )

    # Получаем workflow
    workflow = get_credit_workflow()

    # Конфигурация для checkpointing
    workflow_config = {
        "configurable": {
            "thread_id": application_id
        }
    }

    try:
        logger.info(
            "Starting credit application processing",
            application_id=application_id
        )

        # Запускаем обработку через граф
        final_state = await workflow.ainvoke(
            initial_state,
            config=workflow_config
        )

        logger.info(
            "Credit application processing completed",
            application_id=application_id,
            final_status=final_state["current_step"],
            processing_time=final_state.get("total_processing_time")
        )

        return final_state

    except Exception as e:
        logger.error(
            "Credit application processing failed",
            application_id=application_id,
            error=str(e)
        )
        raise


async def get_application_state(application_id: str) -> dict:
    """Получение текущего состояния обработки заявки"""

    workflow = get_credit_workflow()

    config = {
        "configurable": {
            "thread_id": application_id
        }
    }

    try:
        # Получаем состояние из checkpointer
        state = await workflow.aget_state(config)

        if state.values:
            return state.values
        else:
            logger.warning(
                "No state found for application",
                application_id=application_id
            )
            return None

    except Exception as e:
        logger.error(
            "Failed to get application state",
            application_id=application_id,
            error=str(e)
        )
        raise


async def resume_application_processing(application_id: str) -> dict:
    """Возобновление обработки заявки после прерывания"""

    workflow = get_credit_workflow()

    config = {
        "configurable": {
            "thread_id": application_id
        }
    }

    try:
        logger.info(
            "Resuming application processing",
            application_id=application_id
        )

        # Возобновляем обработку с последнего checkpoint
        final_state = await workflow.ainvoke(None, config)

        logger.info(
            "Application processing resumed and completed",
            application_id=application_id,
            final_status=final_state["current_step"]
        )

        return final_state

    except Exception as e:
        logger.error(
            "Failed to resume application processing",
            application_id=application_id,
            error=str(e)
        )
        raise