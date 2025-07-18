"""
Узел принятия финального решения по кредитной заявке
"""
import math
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime, timedelta

from ..state import CreditApplicationState, ProcessingStatus, add_agent_reasoning, update_processing_step
from ...services.llm_service import llm_service
from ...config.logging import logger


async def decision_node(state: CreditApplicationState) -> CreditApplicationState:
    """
    Узел принятия финального решения по заявке
    """
    logger.info("Starting final decision making", application_id=state["application_id"])

    # Обновляем статус
    state = update_processing_step(state, ProcessingStatus.DECISION_MAKING)

    try:
        # 1. Агрегация всех результатов анализа
        aggregated_results = aggregate_analysis_results(state)

        # 2. Расчет общего скоринга
        overall_scoring = calculate_overall_scoring(aggregated_results)

        # 3. Определение финального решения
        decision_logic = apply_decision_logic(
            aggregated_results,
            overall_scoring,
            state["form_data"]
        )

        # 4. Определение условий кредитования
        credit_conditions = determine_credit_conditions(
            decision_logic,
            state["form_data"],
            aggregated_results
        )

        # 5. LLM валидация решения
        llm_decision_review = await perform_llm_decision_review(
            state["form_data"],
            aggregated_results,
            decision_logic,
            credit_conditions
        )

        # 6. Финализация решения
        final_decision = finalize_decision(
            decision_logic,
            credit_conditions,
            llm_decision_review,
            aggregated_results
        )

        # 7. Создание итогового заключения
        decision_reasoning = create_decision_reasoning(
            final_decision,
            aggregated_results,
            overall_scoring
        )

        # 8. Добавляем рассуждения агента
        state = add_agent_reasoning(
            state,
            "decision_maker",
            decision_reasoning,
            confidence=final_decision["confidence"],
            metadata={
                "decision_status": final_decision["status"],
                "overall_score": overall_scoring["overall_score"],
                "risk_level": final_decision["risk_level"],
                "amount_approved": final_decision.get("amount_approved", 0)
            }
        )

        # 9. Обновляем состояние с финальным решением
        state["final_decision"] = final_decision

        # 10. Завершаем обработку
        if final_decision["status"] == "rejected":
            state = update_processing_step(state, ProcessingStatus.REJECTED)
        else:
            state = update_processing_step(state, ProcessingStatus.COMPLETED)

        logger.info(
            "Final decision completed",
            application_id=state["application_id"],
            decision=final_decision["status"],
            amount_approved=final_decision.get("amount_approved", 0),
            risk_level=final_decision["risk_level"]
        )

        return state

    except Exception as e:
        error_msg = f"Decision making failed: {str(e)}"
        logger.error("Decision making error", application_id=state["application_id"], error=str(e))

        state["errors"].append(error_msg)
        state["final_decision"] = {
            "status": "requires_review",
            "confidence": 0.0,
            "amount_approved": None,
            "conditions": ["Требуется ручная проверка из-за ошибки системы"],
            "reasoning": f"Произошла ошибка при принятии решения: {str(e)}",
            "risk_level": "unknown",
            "expires_at": None
        }

        state = update_processing_step(state, ProcessingStatus.ERROR)
        return state


def aggregate_analysis_results(state: CreditApplicationState) -> Dict[str, Any]:
    """Агрегация результатов всех типов анализа"""

    aggregated = {
        "validation": {
            "completed": False,
            "score": 0.0,
            "status": "not_completed",
            "errors_count": 0,
            "warnings_count": 0
        },
        "legal": {
            "completed": False,
            "score": 0.0,
            "status": "not_completed",
            "risks_count": 0
        },
        "risk": {
            "completed": False,
            "score": 0.0,
            "status": "not_completed",
            "risk_level": "unknown",
            "risks_count": 0
        },
        "relevance": {
            "completed": False,
            "score": 0.0,
            "status": "not_completed",
            "relevance_level": "unknown"
        },
        "financial": {
            "completed": False,
            "score": 0.0,
            "status": "not_completed",
            "stability_level": "unknown"
        },
        "overall_completion": 0.0
    }

    completed_analyses = 0
    total_analyses = 5

    # Валидация
    if state.get("validation_result"):
        validation = state["validation_result"]
        aggregated["validation"] = {
            "completed": True,
            "score": validation.get("score", 0.0),
            "status": validation.get("status", "unknown"),
            "errors_count": len(validation.get("errors", [])),
            "warnings_count": len(validation.get("warnings", []))
        }
        completed_analyses += 1

    # Юридический анализ
    if state.get("legal_analysis"):
        legal = state["legal_analysis"]
        aggregated["legal"] = {
            "completed": True,
            "score": legal.get("score", 0.0),
            "status": legal.get("status", "unknown"),
            "risks_count": len(legal.get("risks", []))
        }
        completed_analyses += 1

    # Анализ рисков
    if state.get("risk_analysis"):
        risk = state["risk_analysis"]
        aggregated["risk"] = {
            "completed": True,
            "score": risk.get("score", 0.0),
            "status": risk.get("status", "unknown"),
            "risk_level": risk.get("details", {}).get("overall_risk_level", "unknown"),
            "risks_count": len(risk.get("risks", []))
        }
        completed_analyses += 1

    # Анализ актуальности
    if state.get("relevance_analysis"):
        relevance = state["relevance_analysis"]
        aggregated["relevance"] = {
            "completed": True,
            "score": relevance.get("score", 0.0),
            "status": relevance.get("status", "unknown"),
            "relevance_level": relevance.get("details", {}).get("relevance_level", "unknown")
        }
        completed_analyses += 1

    # Финансовый анализ
    if state.get("financial_analysis"):
        financial = state["financial_analysis"]
        aggregated["financial"] = {
            "completed": True,
            "score": financial.get("score", 0.0),
            "status": financial.get("status", "unknown"),
            "stability_level": financial.get("details", {}).get("financial_stability_level", "unknown")
        }
        completed_analyses += 1

    aggregated["overall_completion"] = completed_analyses / total_analyses

    return aggregated


def calculate_overall_scoring(aggregated_results: Dict[str, Any]) -> Dict[str, Any]:
    """Расчет общего скоринга по всем анализам"""

    # Веса для разных типов анализа
    weights = {
        "validation": 0.15,  # 15% - базовая валидация
        "legal": 0.20,  # 20% - юридические риски критичны
        "risk": 0.25,  # 25% - общие риски проекта
        "relevance": 0.15,  # 15% - актуальность проекта
        "financial": 0.25  # 25% - финансовая устойчивость критична
    }

    scoring = {
        "component_scores": {},
        "weighted_scores": {},
        "overall_score": 0.0,
        "completion_penalty": 0.0,
        "risk_adjustments": 0.0
    }

    total_weight = 0.0
    weighted_sum = 0.0

    # Собираем оценки по компонентам
    for component, weight in weights.items():
        if aggregated_results[component]["completed"]:
            score = aggregated_results[component]["score"]
            scoring["component_scores"][component] = score
            scoring["weighted_scores"][component] = score * weight

            weighted_sum += score * weight
            total_weight += weight
        else:
            # Штраф за незавершенный анализ
            scoring["component_scores"][component] = 0.0
            scoring["weighted_scores"][component] = 0.0

    # Базовая оценка
    if total_weight > 0:
        base_score = weighted_sum / total_weight
    else:
        base_score = 0.0

    # Штраф за неполноту анализа
    completion_ratio = aggregated_results["overall_completion"]
    if completion_ratio < 1.0:
        completion_penalty = (1.0 - completion_ratio) * 0.3  # Максимум 30% штрафа
        scoring["completion_penalty"] = completion_penalty
        base_score *= (1.0 - completion_penalty)

    # Корректировки на основе критических факторов
    risk_adjustments = calculate_risk_adjustments(aggregated_results)
    scoring["risk_adjustments"] = risk_adjustments

    final_score = max(0.0, min(1.0, base_score + risk_adjustments))
    scoring["overall_score"] = final_score

    # Категоризация общей оценки
    if final_score >= 0.8:
        scoring["score_category"] = "excellent"
    elif final_score >= 0.7:
        scoring["score_category"] = "good"
    elif final_score >= 0.6:
        scoring["score_category"] = "acceptable"
    elif final_score >= 0.4:
        scoring["score_category"] = "poor"
    else:
        scoring["score_category"] = "unacceptable"

    return scoring


def calculate_risk_adjustments(aggregated_results: Dict[str, Any]) -> float:
    """Расчет корректировок на основе критических рисков"""

    adjustments = 0.0

    # Критические ошибки валидации
    if aggregated_results["validation"]["completed"]:
        errors_count = aggregated_results["validation"]["errors_count"]
        if errors_count > 5:
            adjustments -= 0.2  # Серьезный штраф за множественные ошибки
        elif errors_count > 2:
            adjustments -= 0.1

    # Критические юридические риски
    if aggregated_results["legal"]["completed"]:
        if aggregated_results["legal"]["status"] in ["rejected", "blocked"]:
            adjustments -= 0.3  # Юридические проблемы критичны

    # Критические риски проекта
    if aggregated_results["risk"]["completed"]:
        risk_level = aggregated_results["risk"]["risk_level"]
        if risk_level == "critical":
            adjustments -= 0.4  # Максимальный штраф за критические риски
        elif risk_level == "high":
            adjustments -= 0.2

    # Низкая актуальность
    if aggregated_results["relevance"]["completed"]:
        relevance_level = aggregated_results["relevance"]["relevance_level"]
        if relevance_level == "very_low":
            adjustments -= 0.15

    # Критические финансовые проблемы
    if aggregated_results["financial"]["completed"]:
        stability_level = aggregated_results["financial"]["stability_level"]
        if stability_level == "poor":
            adjustments -= 0.3
        elif stability_level == "weak":
            adjustments -= 0.15

    return adjustments


def apply_decision_logic(
        aggregated_results: Dict[str, Any],
        overall_scoring: Dict[str, Any],
        form_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Применение логики принятия решения"""

    decision = {
        "preliminary_status": "requires_review",
        "confidence": 0.0,
        "decision_factors": [],
        "blocking_factors": [],
        "approval_factors": [],
        "conditional_factors": []
    }

    overall_score = overall_scoring["overall_score"]
    completion_ratio = aggregated_results["overall_completion"]

    # Блокирующие факторы (автоматическое отклонение)
    blocking_factors = []

    # 1. Критические ошибки валидации
    if aggregated_results["validation"]["completed"]:
        if aggregated_results["validation"]["errors_count"] > 7:
            blocking_factors.append("Критические ошибки валидации")

    # 2. Юридические блокеры
    if aggregated_results["legal"]["completed"]:
        if aggregated_results["legal"]["status"] in ["rejected", "blocked"]:
            blocking_factors.append("Юридические препятствия")

    # 3. Критические риски
    if aggregated_results["risk"]["completed"]:
        if aggregated_results["risk"]["risk_level"] == "critical":
            blocking_factors.append("Неприемлемый уровень риска")

    # 4. Критические финансовые проблемы
    if aggregated_results["financial"]["completed"]:
        if aggregated_results["financial"]["stability_level"] == "poor":
            blocking_factors.append("Критическое финансовое состояние")

    decision["blocking_factors"] = blocking_factors

    # Если есть блокирующие факторы - отклоняем
    if blocking_factors:
        decision["preliminary_status"] = "rejected"
        decision["confidence"] = 0.9
        return decision

    # Факторы одобрения
    approval_factors = []

    if overall_score >= 0.8:
        approval_factors.append("Отличная общая оценка")
    elif overall_score >= 0.7:
        approval_factors.append("Хорошая общая оценка")

    if aggregated_results["financial"]["completed"]:
        if aggregated_results["financial"]["stability_level"] in ["excellent", "good"]:
            approval_factors.append("Отличная финансовая устойчивость")

    if aggregated_results["legal"]["completed"]:
        if aggregated_results["legal"]["score"] >= 0.8:
            approval_factors.append("Отличная юридическая чистота")

    decision["approval_factors"] = approval_factors

    # Условные факторы
    conditional_factors = []

    if aggregated_results["risk"]["completed"]:
        if aggregated_results["risk"]["risk_level"] == "high":
            conditional_factors.append("Повышенные риски - требуются дополнительные условия")

    if aggregated_results["financial"]["completed"]:
        if aggregated_results["financial"]["stability_level"] == "weak":
            conditional_factors.append("Слабая финансовая устойчивость")

    if completion_ratio < 1.0:
        conditional_factors.append("Неполный анализ")

    decision["conditional_factors"] = conditional_factors

    # Логика принятия решения
    if overall_score >= 0.7 and not conditional_factors:
        decision["preliminary_status"] = "approved"
        decision["confidence"] = 0.9
    elif overall_score >= 0.6 and len(conditional_factors) <= 2:
        decision["preliminary_status"] = "approved"
        decision["confidence"] = 0.7
    elif overall_score >= 0.5:
        decision["preliminary_status"] = "conditional"
        decision["confidence"] = 0.6
    elif overall_score >= 0.3:
        decision["preliminary_status"] = "requires_review"
        decision["confidence"] = 0.5
    else:
        decision["preliminary_status"] = "rejected"
        decision["confidence"] = 0.8

    return decision


def determine_credit_conditions(
        decision_logic: Dict[str, Any],
        form_data: Dict[str, Any],
        aggregated_results: Dict[str, Any]
) -> Dict[str, Any]:
    """Определение условий кредитования"""

    conditions = {
        "approved_amount": 0.0,
        "approval_ratio": 0.0,
        "interest_rate_adjustment": 0.0,
        "term_adjustment_months": 0,
        "additional_conditions": [],
        "guarantees_required": [],
        "monitoring_requirements": []
    }

    requested_amount = form_data.get("requested_amount", 0)
    requested_term = form_data.get("project_duration_months", 0)

    if decision_logic["preliminary_status"] in ["approved", "conditional"]:

        # Базовое одобрение - 100% запрашиваемой суммы
        base_approval_ratio = 1.0

        # Корректировки на основе рисков и финансового состояния

        # 1. Финансовые корректировки
        if aggregated_results["financial"]["completed"]:
            financial_score = aggregated_results["financial"]["score"]
            stability_level = aggregated_results["financial"]["stability_level"]

            if stability_level == "excellent":
                base_approval_ratio = 1.0
            elif stability_level == "good":
                base_approval_ratio = 0.95
            elif stability_level == "acceptable":
                base_approval_ratio = 0.85
            elif stability_level == "weak":
                base_approval_ratio = 0.7
                conditions["additional_conditions"].append("Ежемесячная финансовая отчетность")
                conditions["monitoring_requirements"].append("Усиленный мониторинг финансового состояния")

        # 2. Корректировки на основе рисков
        if aggregated_results["risk"]["completed"]:
            risk_level = aggregated_results["risk"]["risk_level"]

            if risk_level == "high":
                base_approval_ratio *= 0.8
                conditions["interest_rate_adjustment"] += 1.5  # +1.5% к ставке
                conditions["guarantees_required"].append("Дополнительное обеспечение")
            elif risk_level == "medium":
                base_approval_ratio *= 0.9
                conditions["interest_rate_adjustment"] += 0.5  # +0.5% к ставке

        # 3. Юридические требования
        if aggregated_results["legal"]["completed"]:
            legal_score = aggregated_results["legal"]["score"]

            if legal_score < 0.7:
                conditions["additional_conditions"].append("Устранение выявленных юридических замечаний")
                conditions["guarantees_required"].append("Поручительство учредителей")

        # 4. Актуальность проекта
        if aggregated_results["relevance"]["completed"]:
            relevance_level = aggregated_results["relevance"]["relevance_level"]

            if relevance_level == "low":
                base_approval_ratio *= 0.85
                conditions["additional_conditions"].append("Детализация маркетинговой стратегии")

        # Финальные расчеты
        conditions["approval_ratio"] = min(1.0, base_approval_ratio)
        conditions["approved_amount"] = requested_amount * conditions["approval_ratio"]

        # Корректировка срока
        if aggregated_results["financial"]["completed"]:
            if aggregated_results["financial"]["stability_level"] == "weak":
                conditions["term_adjustment_months"] = -12  # Сокращение срока на год

        # Стандартные условия при условном одобрении
        if decision_logic["preliminary_status"] == "conditional":
            conditions["additional_conditions"].extend([
                "Предоставление дополнительной отчетности",
                "Соблюдение финансовых ковенантов"
            ])
            conditions["monitoring_requirements"].extend([
                "Квартальные отчеты о ходе проекта",
                "Мониторинг целевого использования средств"
            ])

    return conditions


async def perform_llm_decision_review(
        form_data: Dict[str, Any],
        aggregated_results: Dict[str, Any],
        decision_logic: Dict[str, Any],
        credit_conditions: Dict[str, Any]
) -> Dict[str, Any]:
    """LLM валидация и обзор принятого решения"""

    system_prompt = """Ты - старший кредитный аналитик банка с 25-летним опытом принятия решений по корпоративным кредитам.

    Проведи финальный обзор кредитного решения, учитывая:
    1. Соответствие решения результатам анализа
    2. Адекватность условий кредитования
    3. Потенциальные риски, которые могли быть упущены
    4. Рекомендации по улучшению условий

    Дай профессиональную оценку решения и предложи корректировки если необходимо.
    Ответь в формате JSON с полями: decision_validation, recommended_adjustments, additional_conditions, risk_concerns, confidence"""

    # Подготавливаем данные для анализа
    review_data = {
        "requested_amount": form_data.get("requested_amount", 0),
        "company_revenue": form_data.get("annual_revenue", 0),
        "project_description": form_data.get("project_description", "")[:200],
        "preliminary_decision": decision_logic["preliminary_status"],
        "overall_score": aggregated_results.get("overall_completion", 0),
        "approved_amount": credit_conditions.get("approved_amount", 0),
        "approval_ratio": credit_conditions.get("approval_ratio", 0),
        "key_risks": decision_logic.get("blocking_factors", []) + decision_logic.get("conditional_factors", [])
    }

    user_message = f"""
    Проведи обзор кредитного решения:

    Заявка:
    - Запрашиваемая сумма: {review_data['requested_amount']:,} тенге
    - Годовая выручка: {review_data['company_revenue']:,} тенге
    - Описание проекта: {review_data['project_description']}

    Предварительное решение:
    - Статус: {review_data['preliminary_decision']}
    - Одобренная сумма: {review_data['approved_amount']:,} тенге
    - Доля одобрения: {review_data['approval_ratio']:.1%}

    Анализ завершенности: {review_data['overall_score']:.1%}

    Ключевые риски: {review_data['key_risks']}

    Оцени корректность решения и предложи улучшения.
    """

    try:
        from langchain_core.messages import SystemMessage, HumanMessage

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message)
        ]

        response = await llm_service.call(messages)
        response_text = response.content

        # Извлекаем JSON из ответа
        import json

        json_start = response_text.find('{')
        json_end = response_text.rfind('}') + 1

        if json_start != -1 and json_end > json_start:
            json_text = response_text[json_start:json_end]
            try:
                llm_result = json.loads(json_text)
            except json.JSONDecodeError:
                llm_result = {
                    "decision_validation": "acceptable",
                    "recommended_adjustments": [],
                    "additional_conditions": [],
                    "risk_concerns": [],
                    "confidence": 0.7
                }
        else:
            # Анализ неструктурированного текста
            validation = "acceptable"
            if "одобряю" in response_text.lower() or "корректно" in response_text.lower():
                validation = "approved"
            elif "отклон" in response_text.lower() or "неправильно" in response_text.lower():
                validation = "rejected"

            llm_result = {
                "decision_validation": validation,
                "recommended_adjustments": [],
                "additional_conditions": [],
                "risk_concerns": [],
                "confidence": 0.6,
                "raw_analysis": response_text
            }

        return {
            "status": "success",
            "validation": llm_result.get("decision_validation", "acceptable"),
            "confidence": llm_result.get("confidence", 0.7),
            "recommended_adjustments": llm_result.get("recommended_adjustments", []),
            "additional_conditions": llm_result.get("additional_conditions", []),
            "risk_concerns": llm_result.get("risk_concerns", []),
            "llm_review": response_text
        }

    except Exception as e:
        logger.error("LLM decision review failed", error=str(e))
        return {
            "status": "error",
            "validation": "acceptable",
            "confidence": 0.5,
            "recommended_adjustments": [],
            "additional_conditions": [],
            "risk_concerns": [f"Ошибка LLM обзора: {str(e)}"],
            "error": str(e)
        }


def finalize_decision(
        decision_logic: Dict[str, Any],
        credit_conditions: Dict[str, Any],
        llm_review: Dict[str, Any],
        aggregated_results: Dict[str, Any]
) -> Dict[str, Any]:
    """Финализация решения с учетом LLM обзора"""

    # Начинаем с предварительного решения
    final_status = decision_logic["preliminary_status"]
    confidence = decision_logic["confidence"]

    # Корректировки на основе LLM обзора
    llm_validation = llm_review.get("validation", "acceptable")

    if llm_validation == "rejected" and final_status == "approved":
        final_status = "requires_review"
        confidence *= 0.7  # Снижаем уверенность
    elif llm_validation == "approved" and final_status == "requires_review":
        final_status = "conditional"
        confidence *= 1.1  # Повышаем уверенность

    # Определяем уровень риска
    risk_level = determine_overall_risk_level(aggregated_results)

    # Собираем все условия
    all_conditions = []
    all_conditions.extend(credit_conditions.get("additional_conditions", []))
    all_conditions.extend(credit_conditions.get("guarantees_required", []))
    all_conditions.extend(credit_conditions.get("monitoring_requirements", []))
    all_conditions.extend(llm_review.get("additional_conditions", []))

    # Устанавливаем срок действия решения
    expires_at = None
    if final_status in ["approved", "conditional"]:
        expires_at = (datetime.now() + timedelta(days=30)).isoformat()

    # Создаем обоснование решения
    reasoning = create_decision_justification(
        final_status,
        aggregated_results,
        decision_logic,
        credit_conditions,
        llm_review
    )

    return {
        "status": final_status,
        "confidence": min(1.0, confidence),
        "amount_approved": credit_conditions.get("approved_amount") if final_status != "rejected" else None,
        "conditions": list(set(all_conditions))[:10],  # Уникальные условия, максимум 10
        "reasoning": reasoning,
        "risk_level": risk_level,
        "expires_at": expires_at
    }


def determine_overall_risk_level(aggregated_results: Dict[str, Any]) -> str:
    """Определение общего уровня риска"""

    risk_factors = []

    # Собираем риски из всех анализов
    if aggregated_results["validation"]["completed"]:
        if aggregated_results["validation"]["errors_count"] > 3:
            risk_factors.append("high")

    if aggregated_results["legal"]["completed"]:
        if aggregated_results["legal"]["score"] < 0.5:
            risk_factors.append("high")
        elif aggregated_results["legal"]["score"] < 0.7:
            risk_factors.append("medium")

    if aggregated_results["risk"]["completed"]:
        risk_level = aggregated_results["risk"]["risk_level"]
        if risk_level == "critical":
            risk_factors.append("critical")
        elif risk_level == "high":
            risk_factors.append("high")
        elif risk_level == "medium":
            risk_factors.append("medium")

    if aggregated_results["financial"]["completed"]:
        stability = aggregated_results["financial"]["stability_level"]
        if stability == "poor":
            risk_factors.append("high")
        elif stability == "weak":
            risk_factors.append("medium")

    if aggregated_results["relevance"]["completed"]:
        relevance = aggregated_results["relevance"]["relevance_level"]
        if relevance == "very_low":
            risk_factors.append("medium")

    # Определяем итоговый уровень
    if "critical" in risk_factors:
        return "critical"
    elif risk_factors.count("high") >= 2:
        return "high"
    elif "high" in risk_factors or risk_factors.count("medium") >= 3:
        return "medium"
    elif "medium" in risk_factors:
        return "low"
    else:
        return "minimal"


def create_decision_justification(
        final_status: str,
        aggregated_results: Dict[str, Any],
        decision_logic: Dict[str, Any],
        credit_conditions: Dict[str, Any],
        llm_review: Dict[str, Any]
) -> str:
    """Создание обоснования решения"""

    justification_parts = []

    # Основание решения
    if final_status == "approved":
        justification_parts.append("✅ РЕШЕНИЕ: Заявка ОДОБРЕНА")
        justification_parts.append("Заявка прошла все этапы анализа с положительными результатами.")
    elif final_status == "conditional":
        justification_parts.append("⚠️ РЕШЕНИЕ: Заявка одобрена УСЛОВНО")
        justification_parts.append("Заявка может быть одобрена при выполнении дополнительных условий.")
    elif final_status == "requires_review":
        justification_parts.append("🔍 РЕШЕНИЕ: Требуется РУЧНАЯ ПРОВЕРКА")
        justification_parts.append("Заявка требует дополнительного анализа специалистами.")
    else:
        justification_parts.append("❌ РЕШЕНИЕ: Заявка ОТКЛОНЕНА")
        justification_parts.append("Выявлены критические риски, препятствующие кредитованию.")

    # Результаты анализа
    justification_parts.append(f"\n📊 Завершенность анализа: {aggregated_results['overall_completion']:.0%}")

    if aggregated_results["validation"]["completed"]:
        score = aggregated_results["validation"]["score"]
        justification_parts.append(f"✓ Валидация: {score:.2f}")

    if aggregated_results["legal"]["completed"]:
        score = aggregated_results["legal"]["score"]
        justification_parts.append(f"✓ Юридическая проверка: {score:.2f}")

    if aggregated_results["risk"]["completed"]:
        score = aggregated_results["risk"]["score"]
        level = aggregated_results["risk"]["risk_level"]
        justification_parts.append(f"✓ Анализ рисков: {score:.2f} (уровень: {level})")

    if aggregated_results["relevance"]["completed"]:
        score = aggregated_results["relevance"]["score"]
        justification_parts.append(f"✓ Актуальность: {score:.2f}")

    if aggregated_results["financial"]["completed"]:
        score = aggregated_results["financial"]["score"]
        level = aggregated_results["financial"]["stability_level"]
        justification_parts.append(f"✓ Финансовый анализ: {score:.2f} (устойчивость: {level})")

    # Ключевые факторы решения
    if decision_logic.get("approval_factors"):
        justification_parts.append(f"\n✅ Факторы одобрения:")
        justification_parts.extend([f"  • {factor}" for factor in decision_logic["approval_factors"]])

    if decision_logic.get("blocking_factors"):
        justification_parts.append(f"\n❌ Блокирующие факторы:")
        justification_parts.extend([f"  • {factor}" for factor in decision_logic["blocking_factors"]])

    if decision_logic.get("conditional_factors"):
        justification_parts.append(f"\n⚠️ Условные факторы:")
        justification_parts.extend([f"  • {factor}" for factor in decision_logic["conditional_factors"]])

    # Условия кредитования
    if final_status in ["approved", "conditional"] and credit_conditions.get("approved_amount"):
        approved_amount = credit_conditions["approved_amount"]
        approval_ratio = credit_conditions["approval_ratio"]
        justification_parts.append(
            f"\n💰 Одобренная сумма: {approved_amount:,.0f} тенге ({approval_ratio:.0%} от запрашиваемой)")

        if credit_conditions.get("interest_rate_adjustment", 0) > 0:
            adjustment = credit_conditions["interest_rate_adjustment"]
            justification_parts.append(f"📈 Корректировка ставки: +{adjustment}%")

    # LLM замечания
    if llm_review.get("risk_concerns"):
        justification_parts.append(f"\n🔍 Дополнительные замечания:")
        justification_parts.extend([f"  • {concern}" for concern in llm_review["risk_concerns"][:3]])

    return "\n".join(justification_parts)


def create_decision_reasoning(
        final_decision: Dict[str, Any],
        aggregated_results: Dict[str, Any],
        overall_scoring: Dict[str, Any]
) -> str:
    """Создание текста рассуждений агента принятия решений"""

    reasoning_parts = []

    # Заголовок с решением
    status = final_decision["status"]
    confidence = final_decision["confidence"]
    risk_level = final_decision["risk_level"]

    if status == "approved":
        reasoning_parts.append(f"✅ ФИНАЛЬНОЕ РЕШЕНИЕ: ЗАЯВКА ОДОБРЕНА (уверенность: {confidence:.0%})")
    elif status == "conditional":
        reasoning_parts.append(f"⚠️ ФИНАЛЬНОЕ РЕШЕНИЕ: УСЛОВНОЕ ОДОБРЕНИЕ (уверенность: {confidence:.0%})")
    elif status == "requires_review":
        reasoning_parts.append(f"🔍 ФИНАЛЬНОЕ РЕШЕНИЕ: ТРЕБУЕТСЯ ПРОВЕРКА (уверенность: {confidence:.0%})")
    else:
        reasoning_parts.append(f"❌ ФИНАЛЬНОЕ РЕШЕНИЕ: ЗАЯВКА ОТКЛОНЕНА (уверенность: {confidence:.0%})")

    reasoning_parts.append(f"🎯 Общий уровень риска: {risk_level.upper()}")

    # Общий скоринг
    overall_score = overall_scoring["overall_score"]
    score_category = overall_scoring["score_category"]

    reasoning_parts.append(f"\n📊 ОБЩИЙ СКОРИНГ: {overall_score:.2f} ({score_category})")

    # Детализация по компонентам
    reasoning_parts.append("\n📋 Результаты анализа по компонентам:")

    for component in ["validation", "legal", "risk", "relevance", "financial"]:
        if aggregated_results[component]["completed"]:
            score = aggregated_results[component]["score"]
            status_comp = aggregated_results[component]["status"]
            reasoning_parts.append(f"  ✓ {component.capitalize()}: {score:.2f} ({status_comp})")
        else:
            reasoning_parts.append(f"  ✗ {component.capitalize()}: НЕ ЗАВЕРШЕН")

    # Одобренная сумма
    if final_decision.get("amount_approved"):
        amount = final_decision["amount_approved"]
        reasoning_parts.append(f"\n💰 Одобренная сумма: {amount:,.0f} тенге")

    # Условия
    conditions = final_decision.get("conditions", [])
    if conditions:
        reasoning_parts.append(f"\n📋 Условия кредитования ({len(conditions)}):")
        reasoning_parts.extend([f"  • {condition}" for condition in conditions[:5]])
        if len(conditions) > 5:
            reasoning_parts.append(f"  • ... и еще {len(conditions) - 5} условий")

    # Срок действия
    if final_decision.get("expires_at"):
        expires = final_decision["expires_at"]
        reasoning_parts.append(f"\n⏰ Решение действительно до: {expires[:10]}")

    # Обоснование
    reasoning_parts.append(f"\n📝 ОБОСНОВАНИЕ:")
    reasoning_parts.append(final_decision.get("reasoning", "Решение принято на основе комплексного анализа."))

    return "\n".join(reasoning_parts)