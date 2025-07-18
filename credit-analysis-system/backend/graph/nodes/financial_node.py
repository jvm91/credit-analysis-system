"""
Узел финансового анализа кредитных заявок
"""
import math
from typing import Dict, Any, List, Tuple
from datetime import datetime, timedelta

from ..state import CreditApplicationState, ProcessingStatus, add_agent_reasoning, update_processing_step
from ...services.llm_service import llm_service
from ...config.logging import logger


async def financial_node(state: CreditApplicationState) -> CreditApplicationState:
    """
    Узел финансового анализа заявки
    """
    logger.info("Starting financial analysis", application_id=state["application_id"])

    # Обновляем статус
    state = update_processing_step(state, ProcessingStatus.FINANCIAL_ANALYZING)

    try:
        # 1. Анализ финансовых коэффициентов
        financial_ratios = await analyze_financial_ratios(state["form_data"])

        # 2. Анализ денежных потоков
        cash_flow_analysis = await analyze_cash_flow(
            state["form_data"],
            state.get("validation_result", {}).get("extracted_data", {})
        )

        # 3. Анализ кредитоспособности
        creditworthiness_analysis = await analyze_creditworthiness(state["form_data"])

        # 4. Анализ долговой нагрузки
        debt_analysis = await analyze_debt_capacity(state["form_data"])

        # 5. LLM анализ финансовой устойчивости
        llm_financial_analysis = await perform_llm_financial_analysis(
            state["form_data"],
            financial_ratios,
            cash_flow_analysis,
            creditworthiness_analysis,
            debt_analysis
        )

        # 6. Прогноз финансового состояния
        financial_forecast = await create_financial_forecast(
            state["form_data"],
            financial_ratios,
            cash_flow_analysis
        )

        # 7. Объединение результатов
        overall_financial_analysis = combine_financial_results(
            financial_ratios,
            cash_flow_analysis,
            creditworthiness_analysis,
            debt_analysis,
            financial_forecast,
            llm_financial_analysis
        )

        # 8. Добавляем рассуждения агента
        reasoning = create_financial_reasoning(overall_financial_analysis)
        state = add_agent_reasoning(
            state,
            "financial_analyzer",
            reasoning,
            confidence=overall_financial_analysis["confidence"],
            metadata={
                "financial_stability_score": overall_financial_analysis["details"]["financial_stability_score"],
                "debt_to_equity": financial_ratios.get("debt_to_equity_ratio", 0),
                "liquidity_ratio": financial_ratios.get("liquidity_ratio", 0),
                "profitability": financial_ratios.get("profitability_score", 0)
            }
        )

        # 9. Обновляем состояние
        state["financial_analysis"] = overall_financial_analysis
        state = update_processing_step(state, ProcessingStatus.FINANCIAL_ANALYSIS_COMPLETE)

        logger.info(
            "Financial analysis completed",
            application_id=state["application_id"],
            score=overall_financial_analysis["score"],
            stability_level=overall_financial_analysis["details"]["financial_stability_level"]
        )

        return state

    except Exception as e:
        error_msg = f"Financial analysis failed: {str(e)}"
        logger.error("Financial analysis error", application_id=state["application_id"], error=str(e))

        state["errors"].append(error_msg)
        state["financial_analysis"] = {
            "status": "error",
            "score": 0.0,
            "confidence": 0.0,
            "summary": "Ошибка при финансовом анализе",
            "details": {"error": str(e), "financial_stability_level": "critical"},
            "recommendations": ["Повторить финансовый анализ"],
            "risks": [error_msg]
        }

        return state


async def analyze_financial_ratios(form_data: Dict[str, Any]) -> Dict[str, Any]:
    """Анализ финансовых коэффициентов"""

    result = {
        "liquidity_ratio": 0.0,
        "debt_to_equity_ratio": 0.0,
        "profitability_score": 0.0,
        "efficiency_score": 0.0,
        "solvency_score": 0.0,
        "ratios_analysis": {}
    }

    # Получаем финансовые данные
    annual_revenue = form_data.get("annual_revenue", 0)
    net_profit = form_data.get("net_profit", 0)
    total_assets = form_data.get("total_assets", 0)
    debt_amount = form_data.get("debt_amount", 0)
    requested_amount = form_data.get("requested_amount", 0)

    # 1. Коэффициент ликвидности (упрощенный расчет)
    if total_assets > 0 and debt_amount >= 0:
        current_assets = total_assets * 0.6  # Предполагаем 60% оборотных активов
        current_liabilities = debt_amount * 0.7  # Предполагаем 70% краткосрочной задолженности

        if current_liabilities > 0:
            liquidity_ratio = current_assets / current_liabilities
        else:
            liquidity_ratio = 2.0  # Хорошая ликвидность при отсутствии долгов

        result["liquidity_ratio"] = liquidity_ratio
        result["ratios_analysis"]["liquidity"] = analyze_liquidity_ratio(liquidity_ratio)

    # 2. Коэффициент долговой нагрузки
    if total_assets > 0 and debt_amount >= 0:
        debt_to_equity_ratio = debt_amount / (total_assets - debt_amount) if (
                                                                                         total_assets - debt_amount) > 0 else float(
            'inf')
        debt_to_equity_ratio = min(debt_to_equity_ratio, 10.0)  # Ограничиваем максимум

        result["debt_to_equity_ratio"] = debt_to_equity_ratio
        result["ratios_analysis"]["debt_burden"] = analyze_debt_ratio(debt_to_equity_ratio)

    # 3. Рентабельность
    if annual_revenue > 0 and net_profit is not None:
        profit_margin = net_profit / annual_revenue

        # Оценка рентабельности от 0 до 1
        if profit_margin >= 0.15:  # 15% и выше - отлично
            profitability_score = 1.0
        elif profit_margin >= 0.10:  # 10-15% - хорошо
            profitability_score = 0.8
        elif profit_margin >= 0.05:  # 5-10% - удовлетворительно
            profitability_score = 0.6
        elif profit_margin >= 0:  # 0-5% - низкая рентабельность
            profitability_score = 0.4
        else:  # Убыточность
            profitability_score = max(0.0, 0.2 + profit_margin)  # Штраф за убытки

        result["profitability_score"] = profitability_score
        result["ratios_analysis"]["profitability"] = {
            "profit_margin": profit_margin,
            "level": get_profitability_level(profit_margin),
            "score": profitability_score
        }

    # 4. Эффективность использования активов
    if total_assets > 0 and annual_revenue > 0:
        asset_turnover = annual_revenue / total_assets

        # Оценка эффективности
        if asset_turnover >= 2.0:  # Высокая оборачиваемость
            efficiency_score = 1.0
        elif asset_turnover >= 1.0:  # Нормальная оборачиваемость
            efficiency_score = 0.8
        elif asset_turnover >= 0.5:  # Низкая оборачиваемость
            efficiency_score = 0.6
        else:  # Очень низкая оборачиваемость
            efficiency_score = 0.4

        result["efficiency_score"] = efficiency_score
        result["ratios_analysis"]["efficiency"] = {
            "asset_turnover": asset_turnover,
            "score": efficiency_score
        }

    # 5. Платежеспособность
    if annual_revenue > 0 and requested_amount > 0:
        # Способность покрыть кредит из выручки
        revenue_coverage = annual_revenue / requested_amount

        if revenue_coverage >= 10:  # Выручка в 10+ раз больше кредита
            solvency_score = 1.0
        elif revenue_coverage >= 5:  # В 5-10 раз
            solvency_score = 0.9
        elif revenue_coverage >= 2:  # В 2-5 раз
            solvency_score = 0.7
        elif revenue_coverage >= 1:  # Примерно равны
            solvency_score = 0.5
        else:  # Кредит больше годовой выручки
            solvency_score = max(0.1, revenue_coverage * 0.4)

        result["solvency_score"] = solvency_score
        result["ratios_analysis"]["solvency"] = {
            "revenue_coverage": revenue_coverage,
            "score": solvency_score
        }

    return result


def analyze_liquidity_ratio(ratio: float) -> Dict[str, Any]:
    """Анализ коэффициента ликвидности"""

    if ratio >= 2.0:
        return {
            "level": "excellent",
            "description": "Отличная ликвидность",
            "score": 1.0,
            "concerns": []
        }
    elif ratio >= 1.5:
        return {
            "level": "good",
            "description": "Хорошая ликвидность",
            "score": 0.8,
            "concerns": []
        }
    elif ratio >= 1.0:
        return {
            "level": "acceptable",
            "description": "Приемлемая ликвидность",
            "score": 0.6,
            "concerns": ["Ликвидность на нижней границе нормы"]
        }
    else:
        return {
            "level": "poor",
            "description": "Низкая ликвидность",
            "score": 0.3,
            "concerns": ["Проблемы с краткосрочной платежеспособностью"]
        }


def analyze_debt_ratio(ratio: float) -> Dict[str, Any]:
    """Анализ коэффициента долговой нагрузки"""

    if ratio <= 0.5:
        return {
            "level": "low",
            "description": "Низкая долговая нагрузка",
            "score": 1.0,
            "concerns": []
        }
    elif ratio <= 1.0:
        return {
            "level": "moderate",
            "description": "Умеренная долговая нагрузка",
            "score": 0.7,
            "concerns": []
        }
    elif ratio <= 2.0:
        return {
            "level": "high",
            "description": "Высокая долговая нагрузка",
            "score": 0.4,
            "concerns": ["Значительная долговая нагрузка"]
        }
    else:
        return {
            "level": "critical",
            "description": "Критическая долговая нагрузка",
            "score": 0.1,
            "concerns": ["Чрезмерная задолженность", "Высокий риск банкротства"]
        }


def get_profitability_level(profit_margin: float) -> str:
    """Определение уровня рентабельности"""

    if profit_margin >= 0.15:
        return "excellent"
    elif profit_margin >= 0.10:
        return "good"
    elif profit_margin >= 0.05:
        return "acceptable"
    elif profit_margin >= 0:
        return "low"
    else:
        return "unprofitable"


async def analyze_cash_flow(form_data: Dict[str, Any], extracted_data: Dict[str, Any]) -> Dict[str, Any]:
    """Анализ денежных потоков"""

    result = {
        "cash_flow_score": 0.5,
        "operating_cash_flow": 0.0,
        "investment_cash_flow": 0.0,
        "financing_cash_flow": 0.0,
        "free_cash_flow": 0.0,
        "cash_flow_stability": "unknown",
        "seasonal_patterns": []
    }

    annual_revenue = form_data.get("annual_revenue", 0)
    net_profit = form_data.get("net_profit", 0)
    requested_amount = form_data.get("requested_amount", 0)
    project_duration_months = form_data.get("project_duration_months", 0)

    # 1. Оценка операционного денежного потока
    if annual_revenue > 0 and net_profit is not None:
        # Приближенная оценка операционного потока (прибыль + амортизация)
        estimated_depreciation = annual_revenue * 0.03  # 3% от выручки
        operating_cash_flow = net_profit + estimated_depreciation

        result["operating_cash_flow"] = operating_cash_flow

        # Оценка качества денежного потока
        if operating_cash_flow > 0:
            cash_flow_margin = operating_cash_flow / annual_revenue

            if cash_flow_margin >= 0.15:
                result["cash_flow_score"] = 0.9
                result["cash_flow_stability"] = "excellent"
            elif cash_flow_margin >= 0.10:
                result["cash_flow_score"] = 0.8
                result["cash_flow_stability"] = "good"
            elif cash_flow_margin >= 0.05:
                result["cash_flow_score"] = 0.6
                result["cash_flow_stability"] = "acceptable"
            else:
                result["cash_flow_score"] = 0.4
                result["cash_flow_stability"] = "weak"
        else:
            result["cash_flow_score"] = 0.2
            result["cash_flow_stability"] = "negative"

    # 2. Анализ способности обслуживать долг
    if operating_cash_flow > 0 and requested_amount > 0 and project_duration_months > 0:
        # Примерный годовой платеж по кредиту (упрощенный расчет)
        annual_payment = requested_amount / (project_duration_months / 12)

        # Коэффициент покрытия долга
        debt_service_coverage = operating_cash_flow / annual_payment

        result["debt_service_coverage"] = debt_service_coverage

        if debt_service_coverage >= 1.5:
            result["debt_capacity"] = "high"
        elif debt_service_coverage >= 1.2:
            result["debt_capacity"] = "adequate"
        elif debt_service_coverage >= 1.0:
            result["debt_capacity"] = "marginal"
        else:
            result["debt_capacity"] = "insufficient"

    # 3. Свободный денежный поток
    if operating_cash_flow > 0:
        # Предполагаем капитальные затраты как 5% от выручки
        estimated_capex = annual_revenue * 0.05
        free_cash_flow = operating_cash_flow - estimated_capex

        result["free_cash_flow"] = free_cash_flow
        result["free_cash_flow_positive"] = free_cash_flow > 0

    # 4. Анализ сезонности (на основе описания проекта)
    project_description = form_data.get("project_description", "").lower()
    seasonal_keywords = {
        "seasonal": ["сезонн", "летн", "зимн", "весенн", "осенн"],
        "agriculture": ["сельское хозяйство", "урожай", "посев"],
        "tourism": ["туризм", "отдых", "курорт"],
        "construction": ["строительство", "ремонт"]
    }

    for category, keywords in seasonal_keywords.items():
        if any(keyword in project_description for keyword in keywords):
            if category in ["seasonal", "agriculture", "tourism"]:
                result["seasonal_patterns"].append(f"Возможная сезонность: {category}")
                result["cash_flow_score"] *= 0.9  # Небольшой штраф за сезонность

    return result


async def analyze_creditworthiness(form_data: Dict[str, Any]) -> Dict[str, Any]:
    """Анализ кредитоспособности"""

    result = {
        "creditworthiness_score": 0.5,
        "credit_factors": [],
        "positive_factors": [],
        "negative_factors": [],
        "credit_rating": "unknown"
    }

    annual_revenue = form_data.get("annual_revenue", 0)
    net_profit = form_data.get("net_profit", 0)
    total_assets = form_data.get("total_assets", 0)
    debt_amount = form_data.get("debt_amount", 0)
    requested_amount = form_data.get("requested_amount", 0)

    score_factors = []

    # 1. Размер бизнеса
    if annual_revenue > 0:
        if annual_revenue >= 1_000_000_000:  # Более 1 млрд
            score_factors.append(0.9)
            result["positive_factors"].append("Крупный бизнес с высокой выручкой")
        elif annual_revenue >= 100_000_000:  # 100 млн - 1 млрд
            score_factors.append(0.8)
            result["positive_factors"].append("Средний/крупный бизнес")
        elif annual_revenue >= 10_000_000:  # 10-100 млн
            score_factors.append(0.6)
            result["credit_factors"].append("Средний бизнес")
        else:  # Менее 10 млн
            score_factors.append(0.4)
            result["negative_factors"].append("Малый бизнес с ограниченной выручкой")

    # 2. Рентабельность
    if annual_revenue > 0 and net_profit is not None:
        profit_margin = net_profit / annual_revenue

        if profit_margin >= 0.10:
            score_factors.append(0.9)
            result["positive_factors"].append(f"Высокая рентабельность: {profit_margin * 100:.1f}%")
        elif profit_margin >= 0.05:
            score_factors.append(0.7)
            result["positive_factors"].append(f"Приемлемая рентабельность: {profit_margin * 100:.1f}%")
        elif profit_margin >= 0:
            score_factors.append(0.5)
            result["credit_factors"].append(f"Низкая рентабельность: {profit_margin * 100:.1f}%")
        else:
            score_factors.append(0.2)
            result["negative_factors"].append(f"Убыточность: {profit_margin * 100:.1f}%")

    # 3. Финансовая устойчивость
    if total_assets > 0 and debt_amount >= 0:
        equity_ratio = (total_assets - debt_amount) / total_assets

        if equity_ratio >= 0.7:
            score_factors.append(0.9)
            result["positive_factors"].append("Высокая доля собственного капитала")
        elif equity_ratio >= 0.5:
            score_factors.append(0.7)
            result["positive_factors"].append("Нормальная доля собственного капитала")
        elif equity_ratio >= 0.3:
            score_factors.append(0.5)
            result["credit_factors"].append("Умеренная доля собственного капитала")
        else:
            score_factors.append(0.3)
            result["negative_factors"].append("Низкая доля собственного капитала")

    # 4. Соотношение кредита к возможностям
    if annual_revenue > 0 and requested_amount > 0:
        credit_to_revenue = requested_amount / annual_revenue

        if credit_to_revenue <= 1.0:
            score_factors.append(0.9)
            result["positive_factors"].append("Консервативный размер кредита")
        elif credit_to_revenue <= 2.0:
            score_factors.append(0.7)
            result["credit_factors"].append("Умеренный размер кредита")
        elif credit_to_revenue <= 5.0:
            score_factors.append(0.5)
            result["negative_factors"].append("Значительный размер кредита")
        else:
            score_factors.append(0.2)
            result["negative_factors"].append("Очень большой размер кредита")

    # 5. Опыт работы (оценка по описанию)
    project_description = form_data.get("project_description", "").lower()
    experience_keywords = ["опыт", "лет работы", "с года", "основана", "работаем"]

    has_experience_mention = any(keyword in project_description for keyword in experience_keywords)
    if has_experience_mention:
        score_factors.append(0.7)
        result["positive_factors"].append("Упоминается опыт работы")
    else:
        score_factors.append(0.5)

    # Расчет общей оценки кредитоспособности
    if score_factors:
        creditworthiness_score = sum(score_factors) / len(score_factors)
        result["creditworthiness_score"] = creditworthiness_score

        # Определение кредитного рейтинга
        if creditworthiness_score >= 0.8:
            result["credit_rating"] = "A"
        elif creditworthiness_score >= 0.7:
            result["credit_rating"] = "B+"
        elif creditworthiness_score >= 0.6:
            result["credit_rating"] = "B"
        elif creditworthiness_score >= 0.5:
            result["credit_rating"] = "B-"
        elif creditworthiness_score >= 0.4:
            result["credit_rating"] = "C+"
        else:
            result["credit_rating"] = "C"

    return result


async def analyze_debt_capacity(form_data: Dict[str, Any]) -> Dict[str, Any]:
    """Анализ долговой емкости"""

    result = {
        "debt_capacity_score": 0.5,
        "maximum_debt_capacity": 0.0,
        "current_debt_utilization": 0.0,
        "available_debt_capacity": 0.0,
        "debt_recommendations": []
    }

    annual_revenue = form_data.get("annual_revenue", 0)
    net_profit = form_data.get("net_profit", 0)
    total_assets = form_data.get("total_assets", 0)
    debt_amount = form_data.get("debt_amount", 0)
    requested_amount = form_data.get("requested_amount", 0)

    # 1. Максимальная долговая емкость на основе выручки
    if annual_revenue > 0:
        # Консервативная оценка: максимум 3 годовых выручки
        max_debt_by_revenue = annual_revenue * 3
        result["maximum_debt_capacity"] = max_debt_by_revenue

    # 2. Максимальная долговая емкость на основе активов
    if total_assets > 0:
        # Максимум 70% от стоимости активов
        max_debt_by_assets = total_assets * 0.7

        # Берем минимум из двух оценок
        if result["maximum_debt_capacity"] > 0:
            result["maximum_debt_capacity"] = min(result["maximum_debt_capacity"], max_debt_by_assets)
        else:
            result["maximum_debt_capacity"] = max_debt_by_assets

    # 3. Текущее использование долговой емкости
    if result["maximum_debt_capacity"] > 0:
        current_debt_utilization = debt_amount / result["maximum_debt_capacity"]
        result["current_debt_utilization"] = min(1.0, current_debt_utilization)

        # Доступная емкость
        available_capacity = result["maximum_debt_capacity"] - debt_amount
        result["available_debt_capacity"] = max(0, available_capacity)

    # 4. Оценка возможности взять новый кредит
    if requested_amount > 0 and result["available_debt_capacity"] > 0:
        if requested_amount <= result["available_debt_capacity"]:
            debt_capacity_score = 0.9
            result["debt_recommendations"].append("Запрашиваемая сумма в пределах долговой емкости")
        elif requested_amount <= result["available_debt_capacity"] * 1.2:  # 20% превышение
            debt_capacity_score = 0.7
            result["debt_recommendations"].append("Небольшое превышение долговой емкости")
        else:
            debt_capacity_score = 0.3
            result["debt_recommendations"].append("Значительное превышение долговой емкости")
            result["debt_recommendations"].append("Рекомендуется снизить запрашиваемую сумму")
    else:
        debt_capacity_score = 0.5

    # 5. Способность обслуживать долг
    if net_profit is not None and net_profit > 0 and requested_amount > 0:
        # Примерная годовая ставка 12%
        annual_interest = requested_amount * 0.12

        if net_profit >= annual_interest * 2:  # Прибыль покрывает проценты в 2 раза
            debt_capacity_score *= 1.1  # Бонус
            result["debt_recommendations"].append("Отличная способность обслуживать долг")
        elif net_profit >= annual_interest:
            result["debt_recommendations"].append("Достаточная способность обслуживать долг")
        else:
            debt_capacity_score *= 0.8  # Штраф
            result["debt_recommendations"].append("Ограниченная способность обслуживать долг")

    result["debt_capacity_score"] = min(1.0, debt_capacity_score)

    return result


async def perform_llm_financial_analysis(
        form_data: Dict[str, Any],
        financial_ratios: Dict[str, Any],
        cash_flow_analysis: Dict[str, Any],
        creditworthiness_analysis: Dict[str, Any],
        debt_analysis: Dict[str, Any]
) -> Dict[str, Any]:
    """LLM анализ финансового состояния"""

    system_prompt = """Ты - ведущий финансовый аналитик с 20-летним опытом в банковском секторе.
    Проанализируй финансовое состояние компании для принятия решения о кредитовании.

    Обрати внимание на:
    1. Финансовую устойчивость и платежеспособность
    2. Качество активов и структуру капитала
    3. Эффективность использования ресурсов
    4. Способность генерировать денежные потоки
    5. Долговую нагрузку и способность обслуживать долг

    Дай профессиональную оценку от 0 до 1 и конкретные рекомендации.
    Ответь в формате JSON с полями: financial_score, stability_level, key_strengths, key_concerns, recommendations"""

    analysis_summary = {
        "company_revenue": form_data.get("annual_revenue", 0),
        "net_profit": form_data.get("net_profit", 0),
        "requested_amount": form_data.get("requested_amount", 0),
        "liquidity_ratio": financial_ratios.get("liquidity_ratio", 0),
        "debt_to_equity": financial_ratios.get("debt_to_equity_ratio", 0),
        "profitability_score": financial_ratios.get("profitability_score", 0),
        "cash_flow_score": cash_flow_analysis.get("cash_flow_score", 0),
        "creditworthiness_score": creditworthiness_analysis.get("creditworthiness_score", 0),
        "debt_capacity_score": debt_analysis.get("debt_capacity_score", 0)
    }

    user_message = f"""
    Проанализируй финансовое состояние компании:

    Финансовые показатели:
    - Годовая выручка: {analysis_summary['company_revenue']:,} тенге
    - Чистая прибыль: {analysis_summary['net_profit']:,} тенге
    - Запрашиваемая сумма: {analysis_summary['requested_amount']:,} тенге

    Коэффициенты:
    - Ликвидность: {analysis_summary['liquidity_ratio']:.2f}
    - Долг/Капитал: {analysis_summary['debt_to_equity']:.2f}
    - Рентабельность: {analysis_summary['profitability_score']:.2f}

    Оценки:
    - Денежные потоки: {analysis_summary['cash_flow_score']:.2f}
    - Кредитоспособность: {analysis_summary['creditworthiness_score']:.2f}
    - Долговая емкость: {analysis_summary['debt_capacity_score']:.2f}

    Дай детальную финансовую оценку и рекомендации по кредитованию.
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
                    "financial_score": 0.6,
                    "stability_level": "moderate",
                    "key_strengths": [],
                    "key_concerns": ["Не удалось получить структурированный анализ"],
                    "recommendations": []
                }
        else:
            # Анализ неструктурированного текста
            score = 0.6
            if any(word in response_text.lower() for word in ["отличн", "высок", "устойчив"]):
                score = 0.8
            elif any(word in response_text.lower() for word in ["низк", "слаб", "проблем"]):
                score = 0.4

            llm_result = {
                "financial_score": score,
                "stability_level": "moderate",
                "key_strengths": [],
                "key_concerns": [],
                "recommendations": [],
                "raw_analysis": response_text
            }

        return {
            "status": "success",
            "score": llm_result.get("financial_score", 0.6),
            "confidence": 0.8,
            "stability_level": llm_result.get("stability_level", "moderate"),
            "key_strengths": llm_result.get("key_strengths", []),
            "key_concerns": llm_result.get("key_concerns", []),
            "recommendations": llm_result.get("recommendations", []),
            "llm_analysis": response_text
        }

    except Exception as e:
        logger.error("LLM financial analysis failed", error=str(e))
        return {
            "status": "error",
            "score": 0.5,
            "confidence": 0.0,
            "stability_level": "unknown",
            "key_strengths": [],
            "key_concerns": [f"Ошибка LLM анализа: {str(e)}"],
            "recommendations": [],
            "error": str(e)
        }


async def create_financial_forecast(
        form_data: Dict[str, Any],
        financial_ratios: Dict[str, Any],
        cash_flow_analysis: Dict[str, Any]
) -> Dict[str, Any]:
    """Создание финансового прогноза"""

    result = {
        "forecast_horizon_years": 3,
        "revenue_growth_forecast": [],
        "profit_forecast": [],
        "cash_flow_forecast": [],
        "debt_service_forecast": [],
        "forecast_reliability": "moderate"
    }

    annual_revenue = form_data.get("annual_revenue", 0)
    net_profit = form_data.get("net_profit", 0)
    requested_amount = form_data.get("requested_amount", 0)
    project_duration_months = form_data.get("project_duration_months", 0)

    # Базовые предположения для прогноза
    if annual_revenue > 0:
        # Прогноз роста выручки (консервативный)
        base_growth_rate = 0.05  # 5% базовый рост

        # Корректировка на основе рентабельности
        profitability_score = financial_ratios.get("profitability_score", 0.5)
        if profitability_score > 0.8:
            growth_rate = 0.08  # 8% для высокорентабельных
        elif profitability_score > 0.6:
            growth_rate = 0.06  # 6% для рентабельных
        else:
            growth_rate = 0.03  # 3% для низкорентабельных

        # Прогноз выручки на 3 года
        for year in range(1, 4):
            forecasted_revenue = annual_revenue * ((1 + growth_rate) ** year)
            result["revenue_growth_forecast"].append({
                "year": year,
                "revenue": forecasted_revenue,
                "growth_rate": growth_rate
            })

    # Прогноз прибыли
    if net_profit is not None and annual_revenue > 0:
        current_margin = net_profit / annual_revenue

        for year, revenue_forecast in enumerate(result["revenue_growth_forecast"], 1):
            # Предполагаем небольшое улучшение маржи за счет эффекта масштаба
            improved_margin = min(current_margin * 1.02, current_margin + 0.01)
            forecasted_profit = revenue_forecast["revenue"] * improved_margin

            result["profit_forecast"].append({
                "year": year,
                "profit": forecasted_profit,
                "margin": improved_margin
            })

    # Прогноз денежных потоков
    operating_cash_flow = cash_flow_analysis.get("operating_cash_flow", 0)
    if operating_cash_flow > 0:
        for year in range(1, 4):
            # Прогноз роста операционного потока
            forecasted_cash_flow = operating_cash_flow * ((1 + growth_rate) ** year)

            result["cash_flow_forecast"].append({
                "year": year,
                "operating_cash_flow": forecasted_cash_flow
            })

    # Прогноз обслуживания долга
    if requested_amount > 0 and project_duration_months > 0:
        annual_payment = requested_amount / (project_duration_months / 12)

        for year in range(1, min(4, int(project_duration_months / 12) + 1)):
            remaining_debt = requested_amount - (annual_payment * (year - 1))

            result["debt_service_forecast"].append({
                "year": year,
                "payment": annual_payment,
                "remaining_debt": max(0, remaining_debt)
            })

    # Оценка надежности прогноза
    reliability_factors = []

    if annual_revenue > 100_000_000:  # Крупный бизнес - более предсказуем
        reliability_factors.append(0.8)
    else:
        reliability_factors.append(0.6)

    if profitability_score > 0.7:  # Стабильная прибыльность
        reliability_factors.append(0.8)
    else:
        reliability_factors.append(0.5)

    if len(reliability_factors) > 0:
        avg_reliability = sum(reliability_factors) / len(reliability_factors)

        if avg_reliability >= 0.8:
            result["forecast_reliability"] = "high"
        elif avg_reliability >= 0.6:
            result["forecast_reliability"] = "moderate"
        else:
            result["forecast_reliability"] = "low"

    return result


def combine_financial_results(
        financial_ratios: Dict[str, Any],
        cash_flow_analysis: Dict[str, Any],
        creditworthiness_analysis: Dict[str, Any],
        debt_analysis: Dict[str, Any],
        financial_forecast: Dict[str, Any],
        llm_analysis: Dict[str, Any]
) -> Dict[str, Any]:
    """Объединение всех результатов финансового анализа"""

    # Веса компонентов
    weights = {
        "ratios": 0.25,
        "cash_flow": 0.25,
        "creditworthiness": 0.20,
        "debt_capacity": 0.15,
        "llm": 0.15
    }

    # Расчет взвешенной оценки
    component_scores = {
        "ratios": (financial_ratios.get("liquidity_ratio", 0) * 0.3 +
                   (1 - min(1, financial_ratios.get("debt_to_equity_ratio", 1))) * 0.3 +
                   financial_ratios.get("profitability_score", 0) * 0.4),
        "cash_flow": cash_flow_analysis.get("cash_flow_score", 0.5),
        "creditworthiness": creditworthiness_analysis.get("creditworthiness_score", 0.5),
        "debt_capacity": debt_analysis.get("debt_capacity_score", 0.5),
        "llm": llm_analysis.get("score", 0.5)
    }

    # Нормализуем оценку коэффициентов
    component_scores["ratios"] = min(1.0, max(0.0, component_scores["ratios"]))

    weighted_score = sum(
        component_scores[component] * weights[component]
        for component in weights.keys()
    )

    # Определение уровня финансовой устойчивости
    if weighted_score >= 0.8:
        stability_level = "excellent"
        status = "approved"
    elif weighted_score >= 0.7:
        stability_level = "good"
        status = "approved"
    elif weighted_score >= 0.6:
        stability_level = "acceptable"
        status = "approved"
    elif weighted_score >= 0.4:
        stability_level = "weak"
        status = "conditional"
    else:
        stability_level = "poor"
        status = "rejected"

    # Собираем ключевые выводы
    key_strengths = []
    key_concerns = []

    # Анализируем сильные стороны
    if component_scores["ratios"] >= 0.7:
        key_strengths.append("Хорошие финансовые коэффициенты")
    if component_scores["cash_flow"] >= 0.7:
        key_strengths.append("Устойчивые денежные потоки")
    if component_scores["creditworthiness"] >= 0.7:
        key_strengths.append("Высокая кредитоспособность")

    # Анализируем проблемы
    if component_scores["ratios"] <= 0.4:
        key_concerns.append("Слабые финансовые показатели")
    if component_scores["cash_flow"] <= 0.4:
        key_concerns.append("Проблемы с денежными потоками")
    if component_scores["debt_capacity"] <= 0.4:
        key_concerns.append("Ограниченная долговая емкость")

    # Добавляем выводы от LLM
    key_strengths.extend(llm_analysis.get("key_strengths", []))
    key_concerns.extend(llm_analysis.get("key_concerns", []))

    # Рекомендации
    recommendations = []
    recommendations.extend(debt_analysis.get("debt_recommendations", []))
    recommendations.extend(llm_analysis.get("recommendations", []))

    if weighted_score < 0.6:
        recommendations.append("Рекомендуется улучшить финансовые показатели")
    if component_scores["cash_flow"] < 0.5:
        recommendations.append("Необходимо укрепить денежные потоки")

    return {
        "status": status,
        "score": weighted_score,
        "confidence": llm_analysis.get("confidence", 0.7),
        "summary": f"Финансовый анализ завершен. Уровень устойчивости: {stability_level}",
        "details": {
            "financial_stability_level": stability_level,
            "financial_stability_score": weighted_score,
            "liquidity_ratio": financial_ratios.get("liquidity_ratio", 0),
            "debt_to_equity_ratio": financial_ratios.get("debt_to_equity_ratio", 0),
            "profitability_score": financial_ratios.get("profitability_score", 0),
            "cash_flow_score": component_scores["cash_flow"],
            "creditworthiness_score": component_scores["creditworthiness"],
            "debt_capacity_score": component_scores["debt_capacity"],
            "component_analysis": {
                "financial_ratios": financial_ratios,
                "cash_flow_analysis": cash_flow_analysis,
                "creditworthiness_analysis": creditworthiness_analysis,
                "debt_analysis": debt_analysis,
                "financial_forecast": financial_forecast,
                "llm_analysis": llm_analysis
            },
            "key_strengths": key_strengths[:5],
            "key_concerns": key_concerns[:5]
        },
        "recommendations": list(set(recommendations))[:6],
        "risks": key_concerns[:5]
    }


def create_financial_reasoning(financial_analysis: Dict[str, Any]) -> str:
    """Создание текста рассуждений финансового агента"""

    score = financial_analysis.get("score", 0.0)
    details = financial_analysis.get("details", {})
    stability_level = details.get("financial_stability_level", "unknown")
    key_strengths = details.get("key_strengths", [])
    key_concerns = details.get("key_concerns", [])
    recommendations = financial_analysis.get("recommendations", [])

    reasoning_parts = []

    # Общая оценка
    if score >= 0.8:
        reasoning_parts.append(f"💰 ОТЛИЧНАЯ финансовая устойчивость: {score:.2f}")
    elif score >= 0.7:
        reasoning_parts.append(f"✅ ХОРОШАЯ финансовая устойчивость: {score:.2f}")
    elif score >= 0.6:
        reasoning_parts.append(f"⚠️ ПРИЕМЛЕМАЯ финансовая устойчивость: {score:.2f}")
    elif score >= 0.4:
        reasoning_parts.append(f"🟡 СЛАБАЯ финансовая устойчивость: {score:.2f}")
    else:
        reasoning_parts.append(f"❌ НЕУДОВЛЕТВОРИТЕЛЬНАЯ финансовая устойчивость: {score:.2f}")

    # Детализация по компонентам
    reasoning_parts.append("\n📊 Финансовые показатели:")
    reasoning_parts.append(f"💧 Ликвидность: {details.get('liquidity_ratio', 0):.2f}")
    reasoning_parts.append(f"📈 Долг/Капитал: {details.get('debt_to_equity_ratio', 0):.2f}")
    reasoning_parts.append(f"💹 Рентабельность: {details.get('profitability_score', 0):.2f}")
    reasoning_parts.append(f"💸 Денежные потоки: {details.get('cash_flow_score', 0):.2f}")
    reasoning_parts.append(f"🏦 Кредитоспособность: {details.get('creditworthiness_score', 0):.2f}")
    reasoning_parts.append(f"📊 Долговая емкость: {details.get('debt_capacity_score', 0):.2f}")

    # Сильные стороны
    if key_strengths:
        reasoning_parts.append(f"\n✅ Сильные стороны ({len(key_strengths)}):")
        reasoning_parts.extend([f"  • {strength}" for strength in key_strengths])

    # Проблемные области
    if key_concerns:
        reasoning_parts.append(f"\n⚠️ Проблемные области ({len(key_concerns)}):")
        reasoning_parts.extend([f"  • {concern}" for concern in key_concerns])

    # Рекомендации
    if recommendations:
        reasoning_parts.append(f"\n💡 Финансовые рекомендации ({len(recommendations)}):")
        reasoning_parts.extend([f"  • {rec}" for rec in recommendations[:4]])

    # Итоговое заключение
    if stability_level == "excellent":
        reasoning_parts.append("\n💰 ЗАКЛЮЧЕНИЕ: Отличная финансовая устойчивость, низкие кредитные риски")
    elif stability_level == "good":
        reasoning_parts.append("\n✅ ЗАКЛЮЧЕНИЕ: Хорошее финансовое состояние, приемлемые риски")
    elif stability_level == "acceptable":
        reasoning_parts.append("\n⚠️ ЗАКЛЮЧЕНИЕ: Удовлетворительная устойчивость, требуется мониторинг")
    elif stability_level == "weak":
        reasoning_parts.append("\n🟡 ЗАКЛЮЧЕНИЕ: Слабая финансовая устойчивость, повышенные риски")
    else:
        reasoning_parts.append("\n❌ ЗАКЛЮЧЕНИЕ: Неудовлетворительное финансовое состояние")

    return "\n".join(reasoning_parts)