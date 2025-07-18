"""
Условная логика маршрутизации между узлами графа
"""
from typing import Literal
from ..state import CreditApplicationState, ProcessingStatus
from ...config.logging import logger


def should_continue_after_validation(
        state: CreditApplicationState
) -> Literal["continue", "reject", "error"]:
    """
    Определяет следующий шаг после валидации
    """
    validation_result = state.get("validation_result")

    if not validation_result:
        logger.warning("No validation result found", application_id=state["application_id"])
        return "error"

    status = validation_result.get("status", "").lower()
    score = validation_result.get("score", 0.0)
    errors = validation_result.get("errors", [])

    # Если есть критические ошибки
    if status == "error" or len(errors) > 5:
        logger.info(
            "Validation failed - rejecting application",
            application_id=state["application_id"],
            status=status,
            errors_count=len(errors)
        )
        return "reject"

    # Если оценка валидации слишком низкая
    if score < 0.6:
        logger.info(
            "Validation score too low - rejecting application",
            application_id=state["application_id"],
            score=score
        )
        return "reject"

    # Если есть предупреждения, но не критичные
    warnings = validation_result.get("warnings", [])
    if len(warnings) > 3:
        logger.warning(
            "Multiple validation warnings detected",
            application_id=state["application_id"],
            warnings_count=len(warnings)
        )
        # Продолжаем, но с осторожностью

    logger.info(
        "Validation passed - continuing to legal check",
        application_id=state["application_id"],
        score=score
    )
    return "continue"


def should_continue_after_legal(
        state: CreditApplicationState
) -> Literal["continue", "reject", "error"]:
    """
    Определяет следующий шаг после юридической проверки
    """
    legal_analysis = state.get("legal_analysis")

    if not legal_analysis:
        logger.warning("No legal analysis result found", application_id=state["application_id"])
        return "error"

    status = legal_analysis.get("status", "").lower()
    score = legal_analysis.get("score", 0.0)
    confidence = legal_analysis.get("confidence", 0.0)
    risks = legal_analysis.get("risks", [])

    # Проверяем на критические юридические риски
    critical_risks = [
        risk for risk in risks
        if "критический" in risk.lower() or "запрет" in risk.lower()
    ]

    if critical_risks:
        logger.info(
            "Critical legal risks detected - rejecting application",
            application_id=state["application_id"],
            critical_risks=critical_risks
        )
        return "reject"

    # Если статус негативный
    if status in ["rejected", "failed", "blocked"]:
        logger.info(
            "Legal check failed - rejecting application",
            application_id=state["application_id"],
            status=status
        )
        return "reject"

    # Если оценка или уверенность слишком низкие
    if score < 0.5 or confidence < 0.6:
        logger.info(
            "Legal analysis score/confidence too low - rejecting application",
            application_id=state["application_id"],
            score=score,
            confidence=confidence
        )
        return "reject"

    logger.info(
        "Legal check passed - continuing to risk analysis",
        application_id=state["application_id"],
        score=score,
        confidence=confidence
    )
    return "continue"


def should_continue_after_risk(
        state: CreditApplicationState
) -> Literal["continue", "reject", "error"]:
    """
    Определяет следующий шаг после анализа рисков
    """
    risk_analysis = state.get("risk_analysis")

    if not risk_analysis:
        logger.warning("No risk analysis result found", application_id=state["application_id"])
        return "error"

    status = risk_analysis.get("status", "").lower()
    score = risk_analysis.get("score", 0.0)
    confidence = risk_analysis.get("confidence", 0.0)
    risks = risk_analysis.get("risks", [])
    details = risk_analysis.get("details", {})

    # Проверяем общий уровень риска
    risk_level = details.get("overall_risk_level", "").lower()
    financial_risk = details.get("financial_risk_score", 0.0)
    market_risk = details.get("market_risk_score", 0.0)
    operational_risk = details.get("operational_risk_score", 0.0)

    # Критический уровень риска
    if risk_level in ["critical", "очень высокий", "неприемлемый"]:
        logger.info(
            "Critical risk level detected - rejecting application",
            application_id=state["application_id"],
            risk_level=risk_level
        )
        return "reject"

    # Высокие финансовые риски
    if financial_risk > 0.8:
        logger.info(
            "High financial risk detected - rejecting application",
            application_id=state["application_id"],
            financial_risk=financial_risk
        )
        return "reject"

    # Множественные высокие риски
    high_risk_count = sum([
        1 for risk_score in [financial_risk, market_risk, operational_risk]
        if risk_score > 0.7
    ])

    if high_risk_count >= 2:
        logger.info(
            "Multiple high risks detected - rejecting application",
            application_id=state["application_id"],
            high_risk_count=high_risk_count
        )
        return "reject"

    # Общая оценка слишком низкая
    if score < 0.4:
        logger.info(
            "Risk analysis score too low - rejecting application",
            application_id=state["application_id"],
            score=score
        )
        return "reject"

    logger.info(
        "Risk analysis passed - continuing to relevance check",
        application_id=state["application_id"],
        score=score,
        risk_level=risk_level
    )
    return "continue"


def should_continue_after_relevance(
        state: CreditApplicationState
) -> Literal["continue", "reject", "error"]:
    """
    Определяет следующий шаг после проверки актуальности
    """
    relevance_analysis = state.get("relevance_analysis")

    if not relevance_analysis:
        logger.warning("No relevance analysis result found", application_id=state["application_id"])
        return "error"

    status = relevance_analysis.get("status", "").lower()
    score = relevance_analysis.get("score", 0.0)
    confidence = relevance_analysis.get("confidence", 0.0)
    details = relevance_analysis.get("details", {})

    # Проверяем актуальность проекта
    market_relevance = details.get("market_relevance_score", 0.0)
    innovation_score = details.get("innovation_score", 0.0)
    economic_impact = details.get("economic_impact_score", 0.0)
    sustainability = details.get("sustainability_score", 0.0)

    # Проект неактуален для рынка
    if market_relevance < 0.3:
        logger.info(
            "Low market relevance - rejecting application",
            application_id=state["application_id"],
            market_relevance=market_relevance
        )
        return "reject"

    # Низкий экономический эффект
    if economic_impact < 0.4:
        logger.info(
            "Low economic impact - rejecting application",
            application_id=state["application_id"],
            economic_impact=economic_impact
        )
        return "reject"

    # Общая оценка актуальности
    if score < 0.5:
        logger.info(
            "Relevance score too low - rejecting application",
            application_id=state["application_id"],
            score=score
        )
        return "reject"

    # Низкая уверенность в анализе
    if confidence < 0.5:
        logger.warning(
            "Low confidence in relevance analysis",
            application_id=state["application_id"],
            confidence=confidence
        )
        # Продолжаем, но отмечаем низкую уверенность

    logger.info(
        "Relevance check passed - continuing to financial analysis",
        application_id=state["application_id"],
        score=score,
        market_relevance=market_relevance
    )
    return "continue"


def should_continue_after_financial(
        state: CreditApplicationState
) -> Literal["continue", "reject", "error"]:
    """
    Определяет следующий шаг после финансового анализа
    """
    financial_analysis = state.get("financial_analysis")

    if not financial_analysis:
        logger.warning("No financial analysis result found", application_id=state["application_id"])
        return "error"

    status = financial_analysis.get("status", "").lower()
    score = financial_analysis.get("score", 0.0)
    confidence = financial_analysis.get("confidence", 0.0)
    details = financial_analysis.get("details", {})

    # Ключевые финансовые показатели
    debt_to_equity = details.get("debt_to_equity_ratio", 0.0)
    liquidity_ratio = details.get("liquidity_ratio", 0.0)
    profitability_score = details.get("profitability_score", 0.0)
    cash_flow_score = details.get("cash_flow_score", 0.0)
    financial_stability = details.get("financial_stability_score", 0.0)

    # Критические финансовые проблемы
    if debt_to_equity > 3.0:  # Слишком высокий долг
        logger.info(
            "Excessive debt-to-equity ratio - rejecting application",
            application_id=state["application_id"],
            debt_to_equity=debt_to_equity
        )
        return "reject"

    if liquidity_ratio < 0.5:  # Проблемы с ликвидностью
        logger.info(
            "Poor liquidity ratio - rejecting application",
            application_id=state["application_id"],
            liquidity_ratio=liquidity_ratio
        )
        return "reject"

    if cash_flow_score < 0.3:  # Проблемы с денежным потоком
        logger.info(
            "Poor cash flow - rejecting application",
            application_id=state["application_id"],
            cash_flow_score=cash_flow_score
        )
        return "reject"

    # Общая финансовая устойчивость
    if financial_stability < 0.4:
        logger.info(
            "Poor financial stability - rejecting application",
            application_id=state["application_id"],
            financial_stability=financial_stability
        )
        return "reject"

    # Общая оценка финансового анализа
    if score < 0.5:
        logger.info(
            "Financial analysis score too low - rejecting application",
            application_id=state["application_id"],
            score=score
        )
        return "reject"

    logger.info(
        "Financial analysis completed - proceeding to final decision",
        application_id=state["application_id"],
        score=score,
        financial_stability=financial_stability
    )
    return "continue"


def calculate_overall_risk_score(state: CreditApplicationState) -> float:
    """
    Вычисляет общий балл риска на основе всех анализов
    """
    scores = []
    weights = {
        "validation": 0.15,
        "legal": 0.25,
        "risk": 0.25,
        "relevance": 0.15,
        "financial": 0.20
    }

    # Собираем оценки из всех анализов
    if state.get("validation_result"):
        scores.append(("validation", state["validation_result"].get("score", 0.0)))

    if state.get("legal_analysis"):
        scores.append(("legal", state["legal_analysis"].get("score", 0.0)))

    if state.get("risk_analysis"):
        # Инвертируем оценку риска (высокий риск = низкая оценка)
        risk_score = 1.0 - state["risk_analysis"].get("score", 1.0)
        scores.append(("risk", risk_score))

    if state.get("relevance_analysis"):
        scores.append(("relevance", state["relevance_analysis"].get("score", 0.0)))

    if state.get("financial_analysis"):
        scores.append(("financial", state["financial_analysis"].get("score", 0.0)))

    # Вычисляем взвешенную оценку
    if not scores:
        return 0.0

    weighted_sum = sum(weights.get(category, 0.0) * score for category, score in scores)
    total_weight = sum(weights.get(category, 0.0) for category, _ in scores)

    if total_weight == 0:
        return 0.0

    overall_score = weighted_sum / total_weight

    logger.info(
        "Overall risk score calculated",
        application_id=state["application_id"],
        overall_score=overall_score,
        component_scores=dict(scores)
    )

    return overall_score


def get_rejection_reasons(state: CreditApplicationState) -> list:
    """
    Собирает причины отклонения заявки из всех анализов
    """
    reasons = []

    # Проверяем результаты валидации
    if state.get("validation_result"):
        validation = state["validation_result"]
        if validation.get("score", 1.0) < 0.6:
            reasons.append(f"Низкая оценка валидации: {validation.get('score', 0):.2f}")

        errors = validation.get("errors", [])
        if errors:
            reasons.extend([f"Ошибка валидации: {error}" for error in errors[:3]])

    # Проверяем юридический анализ
    if state.get("legal_analysis"):
        legal = state["legal_analysis"]
        if legal.get("score", 1.0) < 0.5:
            reasons.append(f"Низкая оценка юридической проверки: {legal.get('score', 0):.2f}")

        risks = legal.get("risks", [])
        critical_legal_risks = [risk for risk in risks if "критический" in risk.lower()]
        if critical_legal_risks:
            reasons.extend(critical_legal_risks[:2])

    # Проверяем анализ рисков
    if state.get("risk_analysis"):
        risk = state["risk_analysis"]
        details = risk.get("details", {})
        risk_level = details.get("overall_risk_level", "")

        if risk_level.lower() in ["critical", "очень высокий"]:
            reasons.append(f"Критический уровень риска: {risk_level}")

        if details.get("financial_risk_score", 0) > 0.8:
            reasons.append("Высокий финансовый риск")

    # Проверяем анализ актуальности
    if state.get("relevance_analysis"):
        relevance = state["relevance_analysis"]
        if relevance.get("score", 1.0) < 0.5:
            reasons.append(f"Низкая актуальность проекта: {relevance.get('score', 0):.2f}")

    # Проверяем финансовый анализ
    if state.get("financial_analysis"):
        financial = state["financial_analysis"]
        details = financial.get("details", {})

        if details.get("debt_to_equity_ratio", 0) > 3.0:
            reasons.append("Избыточный уровень задолженности")

        if details.get("liquidity_ratio", 1.0) < 0.5:
            reasons.append("Низкая ликвидность")

        if details.get("financial_stability_score", 1.0) < 0.4:
            reasons.append("Низкая финансовая устойчивость")

    return reasons[:5]  # Ограничиваем до 5 основных причин