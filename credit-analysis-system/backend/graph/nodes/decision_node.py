"""
Узел принятия итогового решения по кредитной заявке
"""
import math
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from ..state import CreditApplicationState, ProcessingStatus, add_agent_reasoning, update_processing_step
from ...services.llm_service import llm_service
from ...config.logging import logger


async def decision_node(state: CreditApplicationState) -> CreditApplicationState:
    """
    Узел принятия итогового решения по кредитной заявке
    """
    logger.info("Starting final decision making", application_id=state["application_id"])

    # Обновляем статус
    state = update_processing_step(state, ProcessingStatus.DECISION_MAKING)

    try:
        # 1. Сбор всех результатов анализа
        analysis_results = collect_analysis_results(state)

        # 2. Расчет интегральной оценки
        overall_assessment = calculate_overall_assessment(analysis_results)

        # 3. Определение базового решения на основе оценок
        base_decision = determine_base_decision(overall_assessment, state["form_data"])

        # 4. LLM анализ для итогового решения
        llm_decision_analysis = await perform_llm_decision_analysis(
            state["form_data"],
            analysis_results,
            overall_assessment,
            base_decision
        )

        # 5. Формирование условий кредитования
        credit_conditions = generate_credit_conditions(
            overall_assessment,
            base_decision,
            state["form_data"]
        )

        # 6. Создание итогового решения
        final_decision = create_final_decision(
            base_decision,
            overall_assessment,
            credit_conditions,
            llm_decision_analysis,
            state["form_data"]
        )

        # 7. Добавляем рассуждения агента
        reasoning = create_decision_reasoning(
            final_decision,
            overall_assessment,
            analysis_results
        )
        state = add_agent_reasoning(
            state,
            "decision_maker",
            reasoning,
            confidence=final_decision["confidence"],
            metadata={
                "overall_score": overall_assessment["overall_score"],
                "decision_status": final_decision["status"],
                "approved_amount": final_decision.get("amount_approved"),
                "conditions_count": len(final_decision.get("conditions", []))
            }
        )

        # 8. Обновляем состояние с итоговым решением
        state["final_decision"] = final_decision
        state = update_processing_step(state, ProcessingStatus.COMPLETED)

        logger.info(
            "Final decision completed",
            application_id=state["application_id"],
            decision=final_decision["status"],
            confidence=final_decision["confidence"],
            approved_amount=final_decision.get("amount_approved")
        )

        return state

    except Exception as e:
        error_msg = f"Decision making failed: {str(e)}"
        logger.error("Decision making error", application_id=state["application_id"], error=str(e))

        state["errors"].append(error_msg)
        state["final_decision"] = {
            "status": "error",
            "confidence": 0.0,
            "amount_approved": None,
            "conditions": [],
            "reasoning": f"Ошибка при принятии решения: {str(e)}",
            "risk_level": "critical",
            "expires_at": None
        }
        state = update_processing_step(state, ProcessingStatus.ERROR)

        return state


def collect_analysis_results(state: CreditApplicationState) -> Dict[str, Any]:
    """Сбор всех результатов анализа из состояния"""

    return {
        "validation": state.get("validation_result", {}),
        "legal": state.get("legal_analysis", {}),
        "risk": state.get("risk_analysis", {}),
        "relevance": state.get("relevance_analysis", {}),
        "financial": state.get("financial_analysis", {}),
        "errors": state.get("errors", []),
        "warnings": state.get("warnings", [])
    }


def calculate_overall_assessment(analysis_results: Dict[str, Any]) -> Dict[str, Any]:
    """Расчет интегральной оценки на основе всех анализов"""

    # Веса для различных типов анализа
    weights = {
        "validation": 0.15,
        "legal": 0.20,
        "risk": 0.25,
        "relevance": 0.15,
        "financial": 0.25
    }

    # Минимальные пороги для каждого типа анализа
    min_thresholds = {
        "validation": 0.6,
        "legal": 0.5,
        "risk": 0.4,
        "relevance": 0.4,
        "financial": 0.4
    }

    scores = {}
    critical_failures = []
    warnings = []

    # Собираем оценки из каждого анализа
    for analysis_type, weight in weights.items():
        analysis_data = analysis_results.get(analysis_type, {})
        score = analysis_data.get("score", 0.0)
        status = analysis_data.get("status", "unknown")

        scores[analysis_type] = score

        # Проверяем критические провалы
        if score < min_thresholds[analysis_type]:
            critical_failures.append({
                "analysis": analysis_type,
                "score": score,
                "threshold": min_thresholds[analysis_type],
                "description": f"{analysis_type} не прошел минимальный порог"
            })

        # Проверяем статус ошибки
        if status == "error":
            critical_failures.append({
                "analysis": analysis_type,
                "score": 0.0,
                "threshold": min_thresholds[analysis_type],
                "description": f"Ошибка в {analysis_type} анализе"
            })

        # Предупреждения для низких оценок
        if 0.3 <= score < min_thresholds[analysis_type]:
            warnings.append(f"Низкая оценка {analysis_type}: {score:.2f}")

    # Расчет взвешенной оценки
    if scores:
        weighted_score = sum(scores[key] * weights[key] for key in scores.keys())
        average_score = sum(scores.values()) / len(scores)
    else:
        weighted_score = 0.0
        average_score = 0.0

    # Штрафы за критические провалы
    penalty = len(critical_failures) * 0.1
    final_score = max(0.0, weighted_score - penalty)

    # Определение общего уровня риска
    if final_score >= 0.8 and not critical_failures:
        risk_level = "low"
        recommendation = "approved"
    elif final_score >= 0.6 and len(critical_failures) <= 1:
        risk_level = "moderate"
        recommendation = "conditional"
    elif final_score >= 0.4 and len(critical_failures) <= 2:
        risk_level = "high"
        recommendation = "requires_review"
    else:
        risk_level = "critical"
        recommendation = "rejected"

    return {
        "overall_score": final_score,
        "weighted_score": weighted_score,
        "average_score": average_score,
        "component_scores": scores,
        "critical_failures": critical_failures,
        "warnings": warnings,
        "risk_level": risk_level,
        "recommendation": recommendation,
        "weights": weights
    }


def determine_base_decision(overall_assessment: Dict[str, Any], form_data: Dict[str, Any]) -> Dict[str, Any]:
    """Определение базового решения на основе интегральной оценки"""

    overall_score = overall_assessment["overall_score"]
    critical_failures = overall_assessment["critical_failures"]
    risk_level = overall_assessment["risk_level"]
    recommendation = overall_assessment["recommendation"]

    requested_amount = form_data.get("requested_amount", 0)
    project_duration = form_data.get("project_duration_months", 12)

    # Базовое решение
    if recommendation == "approved" and len(critical_failures) == 0:
        status = "approved"
        amount_approved = requested_amount
        confidence = min(0.95, 0.7 + overall_score * 0.25)
    elif recommendation == "conditional" and len(critical_failures) <= 1:
        status = "conditional_approval"
        # Возможно снижение суммы на 10-30%
        reduction_factor = 1.0 - (len(critical_failures) * 0.1 + (0.8 - overall_score) * 0.5)
        amount_approved = requested_amount * max(0.7, reduction_factor)
        confidence = min(0.85, 0.5 + overall_score * 0.35)
    elif recommendation == "requires_review":
        status = "requires_review"
        # Значительное снижение суммы
        amount_approved = requested_amount * max(0.5, overall_score)
        confidence = min(0.7, 0.3 + overall_score * 0.4)
    else:
        status = "rejected"
        amount_approved = 0
        confidence = min(0.9, 0.7 + (1.0 - overall_score) * 0.2)

    # Определение срока действия решения
    if status == "approved":
        expires_in_days = 90  # 3 месяца
    elif status in ["conditional_approval", "requires_review"]:
        expires_in_days = 60  # 2 месяца
    else:
        expires_in_days = 30  # 1 месяц для отклонения

    expires_at = datetime.now() + timedelta(days=expires_in_days)

    return {
        "status": status,
        "amount_approved": amount_approved,
        "confidence": confidence,
        "expires_at": expires_at.isoformat(),
        "risk_level": risk_level,
        "base_reasoning": f"Решение основано на общей оценке {overall_score:.2f} и {len(critical_failures)} критических проблемах"
    }


async def perform_llm_decision_analysis(
        form_data: Dict[str, Any],
        analysis_results: Dict[str, Any],
        overall_assessment: Dict[str, Any],
        base_decision: Dict[str, Any]
) -> Dict[str, Any]:
    """LLM анализ для принятия итогового решения"""

    system_prompt = """Ты - опытный кредитный комитет банка с многолетним опытом принятия решений.
    На основе всех проведенных анализов прими взвешенное решение по кредитной заявке.

    Учти:
    1. Результаты всех анализов (валидация, юридический, риски, актуальность, финансы)
    2. Общую оценку риска проекта
    3. Потенциальную доходность для фонда
    4. Соответствие целям и миссии фонда развития
    5. Возможные условия и ограничения

    Дай финальную рекомендацию и обоснование.
    Ответь в формате JSON с полями: final_recommendation, reasoning, suggested_conditions, risk_mitigation"""

    # Подготавливаем сводку для LLM
    summary = {
        "company": form_data.get("company_name", ""),
        "project": form_data.get("project_name", ""),
        "requested_amount": form_data.get("requested_amount", 0),
        "duration_months": form_data.get("project_duration_months", 0),
        "overall_score": overall_assessment["overall_score"],
        "risk_level": overall_assessment["risk_level"],
        "base_recommendation": base_decision["status"],
        "component_scores": overall_assessment["component_scores"],
        "critical_issues": len(overall_assessment["critical_failures"])
    }

    user_message = f"""
    Рассмотри кредитную заявку и прими решение:

    ЗАЯВКА:
    - Компания: {form_data.get('company_name', '')}
    - Проект: {form_data.get('project_name', '')}
    - Сумма: {form_data.get('requested_amount', 0):,} тенге
    - Срок: {form_data.get('project_duration_months', 0)} месяцев
    - Описание: {form_data.get('project_description', '')[:300]}...

    РЕЗУЛЬТАТЫ АНАЛИЗА:
    - Общая оценка: {overall_assessment['overall_score']:.2f} из 1.0
    - Уровень риска: {overall_assessment['risk_level']}
    - Валидация: {overall_assessment['component_scores'].get('validation', 0):.2f}
    - Юридический анализ: {overall_assessment['component_scores'].get('legal', 0):.2f}
    - Анализ рисков: {overall_assessment['component_scores'].get('risk', 0):.2f}
    - Актуальность: {overall_assessment['component_scores'].get('relevance', 0):.2f}
    - Финансовый анализ: {overall_assessment['component_scores'].get('financial', 0):.2f}

    КРИТИЧЕСКИЕ ПРОБЛЕМЫ: {len(overall_assessment['critical_failures'])}
    БАЗОВАЯ РЕКОМЕНДАЦИЯ: {base_decision['status']}

    Дай финальное решение с обоснованием и условиями.
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
                    "final_recommendation": base_decision["status"],
                    "reasoning": "Не удалось получить структурированный анализ от LLM",
                    "suggested_conditions": [],
                    "risk_mitigation": []
                }
        else:
            # Анализ неструктурированного текста
            if "одобрить" in response_text.lower() or "approved" in response_text.lower():
                recommendation = "approved"
            elif "отклонить" in response_text.lower() or "rejected" in response_text.lower():
                recommendation = "rejected"
            elif "условно" in response_text.lower() or "conditional" in response_text.lower():
                recommendation = "conditional_approval"
            else:
                recommendation = base_decision["status"]

            llm_result = {
                "final_recommendation": recommendation,
                "reasoning": response_text[:500],
                "suggested_conditions": [],
                "risk_mitigation": [],
                "raw_analysis": response_text
            }

        return {
            "status": "success",
            "recommendation": llm_result.get("final_recommendation", base_decision["status"]),
            "confidence": 0.7,
            "reasoning": llm_result.get("reasoning", ""),
            "suggested_conditions": llm_result.get("suggested_conditions", []),
            "risk_mitigation": llm_result.get("risk_mitigation", []),
            "llm_analysis": response_text
        }

    except Exception as e:
        logger.error("LLM decision analysis failed", error=str(e))
        return {
            "status": "error",
            "recommendation": base_decision["status"],
            "confidence": 0.0,
            "reasoning": f"Ошибка LLM анализа: {str(e)}",
            "suggested_conditions": [],
            "risk_mitigation": [],
            "error": str(e)
        }


def generate_credit_conditions(
        overall_assessment: Dict[str, Any],
        base_decision: Dict[str, Any],
        form_data: Dict[str, Any]
) -> List[str]:
    """Генерация условий кредитования"""

    conditions = []
    overall_score = overall_assessment["overall_score"]
    critical_failures = overall_assessment["critical_failures"]
    risk_level = overall_assessment["risk_level"]

    # Базовые условия в зависимости от риска
    if risk_level == "low":
        conditions.extend([
            "Стандартные условия кредитования",
            "Ежемесячная отчетность о ходе проекта"
        ])
    elif risk_level == "moderate":
        conditions.extend([
            "Усиленный мониторинг реализации проекта",
            "Ежемесячная финансовая отчетность",
            "Целевое использование средств"
        ])
    elif risk_level == "high":
        conditions.extend([
            "Поэтапное финансирование по достижению контрольных точек",
            "Еженедельная отчетность",
            "Дополнительные гарантии или залог",
            "Согласование ключевых решений с фондом"
        ])
    else:  # critical
        conditions.extend([
            "Критический уровень риска",
            "Требуется кардинальная доработка проекта",
            "Дополнительная экспертиза"
        ])

    # Условия на основе конкретных проблем
    for failure in critical_failures:
        analysis_type = failure["analysis"]

        if analysis_type == "validation":
            conditions.append("Доработка и повторная подача документов")
        elif analysis_type == "legal":
            conditions.append("Устранение юридических нарушений")
        elif analysis_type == "risk":
            conditions.append("Представление плана снижения рисков")
        elif analysis_type == "financial":
            conditions.append("Улучшение финансовых показателей")
        elif analysis_type == "relevance":
            conditions.append("Обоснование актуальности и значимости проекта")

    # Финансовые условия
    requested_amount = form_data.get("requested_amount", 0)
    if requested_amount > 1_000_000_000:  # Более 1 млрд
        conditions.append("Обязательное страхование рисков проекта")
        conditions.append("Создание резервного фонда в размере 10% от суммы кредита")

    # Временные ограничения
    project_duration = form_data.get("project_duration_months", 0)
    if project_duration > 60:  # Более 5 лет
        conditions.append("Ежегодный пересмотр условий кредитования")
        conditions.append("Промежуточная оценка эффективности каждые 2 года")

    # Отраслевые условия
    project_description = form_data.get("project_description", "").lower()
    if any(word in project_description for word in ["экспорт", "международный"]):
        conditions.append("Валютное хеджирование рисков")

    if any(word in project_description for word in ["производство", "строительство"]):
        conditions.append("Обязательное получение всех разрешений до начала финансирования")

    return list(set(conditions))  # Убираем дубликаты


def create_final_decision(
        base_decision: Dict[str, Any],
        overall_assessment: Dict[str, Any],
        credit_conditions: List[str],
        llm_analysis: Dict[str, Any],
        form_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Создание итогового решения"""

    # LLM может скорректировать базовое решение
    llm_recommendation = llm_analysis.get("recommendation", base_decision["status"])

    # Финальный статус (LLM имеет приоритет, но не может ухудшить критические случаи)
    if overall_assessment["overall_score"] < 0.3:
        final_status = "rejected"  # Критически низкая оценка
    elif len(overall_assessment["critical_failures"]) >= 3:
        final_status = "rejected"  # Слишком много критических проблем
    else:
        final_status = llm_recommendation

    # Корректировка суммы
    if final_status == "approved":
        amount_approved = base_decision["amount_approved"]
    elif final_status == "conditional_approval":
        amount_approved = base_decision["amount_approved"] * 0.8  # Снижение на 20%
    elif final_status == "requires_review":
        amount_approved = base_decision["amount_approved"] * 0.6  # Снижение на 40%
    else:
        amount_approved = None

    # Объединение условий
    all_conditions = credit_conditions.copy()
    all_conditions.extend(llm_analysis.get("suggested_conditions", []))

    # Создание итогового обоснования
    reasoning_parts = [
        f"Общая оценка проекта: {overall_assessment['overall_score']:.2f}",
        f"Уровень риска: {overall_assessment['risk_level']}",
        base_decision["base_reasoning"]
    ]

    if llm_analysis.get("reasoning"):
        reasoning_parts.append(f"Экспертное заключение: {llm_analysis['reasoning']}")

    if overall_assessment["critical_failures"]:
        reasoning_parts.append(
            f"Критические проблемы ({len(overall_assessment['critical_failures'])}): " +
            ", ".join([f["description"] for f in overall_assessment["critical_failures"][:3]])
        )

    return {
        "status": final_status,
        "confidence": min(base_decision["confidence"], llm_analysis.get("confidence", 1.0)),
        "amount_approved": amount_approved,
        "conditions": list(set(all_conditions))[:10],  # Максимум 10 условий
        "reasoning": " | ".join(reasoning_parts),
        "risk_level": overall_assessment["risk_level"],
        "expires_at": base_decision["expires_at"],
        "decision_date": datetime.now().isoformat(),
        "overall_score": overall_assessment["overall_score"],
        "component_breakdown": overall_assessment["component_scores"]
    }


def create_decision_reasoning(
        final_decision: Dict[str, Any],
        overall_assessment: Dict[str, Any],
        analysis_results: Dict[str, Any]
) -> str:
    """Создание текста рассуждений агента принятия решений"""

    status = final_decision["status"]
    confidence = final_decision["confidence"]
    overall_score = overall_assessment["overall_score"]
    amount_approved = final_decision.get("amount_approved")
    conditions = final_decision.get("conditions", [])

    reasoning_parts = []

    # Заголовок с итоговым решением
    status_icons = {
        "approved": "✅ ОДОБРЕНО",
        "conditional_approval": "⚠️ УСЛОВНОЕ ОДОБРЕНИЕ",
        "requires_review": "🔍 ТРЕБУЕТ ДОПОЛНИТЕЛЬНОГО РАССМОТРЕНИЯ",
        "rejected": "❌ ОТКЛОНЕНО"
    }

    reasoning_parts.append(f"🏆 ИТОГОВОЕ РЕШЕНИЕ: {status_icons.get(status, status)}")
    reasoning_parts.append(f"📊 Общая оценка: {overall_score:.2f} из 1.0")
    reasoning_parts.append(f"🎯 Уверенность в решении: {confidence:.1%}")

    # Одобренная сумма
    if amount_approved:
        requested = final_decision.get("component_breakdown", {})
        reasoning_parts.append(f"💰 Одобренная сумма: {amount_approved:,.0f} тенге")

        # Показываем изменение суммы если есть
        original_amount = None
        for result in analysis_results.values():
            if isinstance(result, dict) and "form_data" in str(result):
                break
        # Упрощенно показываем процент одобрения
        reasoning_parts.append(f"📈 Процент одобрения: {(amount_approved/10000000)*100 if amount_approved else 0:.0f}%")

    # Детализация по компонентам
    reasoning_parts.append("\n📋 Результаты анализа по компонентам:")
    component_scores = overall_assessment.get("component_scores", {})

    for component, score in component_scores.items():
        emoji_map = {
            "validation": "📝",
            "legal": "⚖️",
            "risk": "⚠️",
            "relevance": "🎯",
            "financial": "💰"
        }
        emoji = emoji_map.get(component, "📊")
        status_text = "✅" if score >= 0.6 else "⚠️" if score >= 0.4 else "❌"
        reasoning_parts.append(f"  {emoji} {component.title()}: {score:.2f} {status_text}")

    # Критические проблемы
    critical_failures = overall_assessment.get("critical_failures", [])
    if critical_failures:
        reasoning_parts.append(f"\n🚨 Критические проблемы ({len(critical_failures)}):")
        for failure in critical_failures[:3]:
            reasoning_parts.append(f"  • {failure['description']}")
        if len(critical_failures) > 3:
            reasoning_parts.append(f"  • ... и еще {len(critical_failures) - 3}")

    # Условия кредитования
    if conditions:
        reasoning_parts.append(f"\n📜 Условия кредитования ({len(conditions)}):")
        for condition in conditions[:5]:
            reasoning_parts.append(f"  • {condition}")
        if len(conditions) > 5:
            reasoning_parts.append(f"  • ... и еще {len(conditions) - 5} условий")

    # Срок действия решения
    if final_decision.get("expires_at"):
        reasoning_parts.append(f"\n⏰ Решение действует до: {final_decision['expires_at'][:10]}")

    # Финальное обоснование
    reasoning_parts.append(f"\n🎯 ОБОСНОВАНИЕ:")

    if status == "approved":
        reasoning_parts.append("Проект соответствует всем требованиям фонда, финансовые и качественные показатели на высоком уровне.")
    elif status == "conditional_approval":
        reasoning_parts.append("Проект имеет хороший потенциал, но требует выполнения дополнительных условий для снижения рисков.")
    elif status == "requires_review":
        reasoning_parts.append("Проект требует доработки и дополнительной экспертизы перед принятием окончательного решения.")
    else:
        reasoning_parts.append("Проект не соответствует критериям фонда или имеет неприемлемый уровень рисков.")

    return "\n".join(reasoning_parts)