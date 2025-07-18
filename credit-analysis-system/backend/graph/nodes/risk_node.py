"""
Узел анализа рисков кредитных заявок
"""
import math
from typing import Dict, Any, List
from datetime import datetime

from ..state import CreditApplicationState, ProcessingStatus, add_agent_reasoning, update_processing_step
from ...services.llm_service import llm_service
from ...config.logging import logger


async def risk_node(state: CreditApplicationState) -> CreditApplicationState:
    """
    Узел анализа рисков проекта
    """
    logger.info("Starting risk analysis", application_id=state["application_id"])

    # Обновляем статус
    state = update_processing_step(state, ProcessingStatus.RISK_ANALYZING)

    try:
        # 1. Финансовый анализ рисков
        financial_risks = await analyze_financial_risks(state["form_data"])

        # 2. Рыночные риски
        market_risks = await analyze_market_risks(
            state["form_data"],
            state.get("validation_result", {}).get("extracted_data", {})
        )

        # 3. Операционные риски
        operational_risks = await analyze_operational_risks(state["form_data"])

        # 4. LLM анализ комплексных рисков
        llm_risk_analysis = await perform_llm_risk_analysis(
            state["form_data"],
            financial_risks,
            market_risks,
            operational_risks
        )

        # 5. Анализ истории компании и менеджмента
        management_risks = await analyze_management_risks(
            state["form_data"],
            state.get("validation_result", {}).get("extracted_data", {})
        )

        # 6. Объединение и оценка общих рисков
        overall_risk_analysis = combine_risk_results(
            financial_risks,
            market_risks,
            operational_risks,
            management_risks,
            llm_risk_analysis
        )

        # 7. Добавляем рассуждения агента
        reasoning = create_risk_reasoning(overall_risk_analysis)
        state = add_agent_reasoning(
            state,
            "risk_manager",
            reasoning,
            confidence=overall_risk_analysis["confidence"],
            metadata={
                "financial_risk": financial_risks["risk_level"],
                "market_risk": market_risks["risk_level"],
                "operational_risk": operational_risks["risk_level"],
                "overall_risk": overall_risk_analysis["details"]["overall_risk_level"]
            }
        )

        # 8. Обновляем состояние
        state["risk_analysis"] = overall_risk_analysis
        state = update_processing_step(state, ProcessingStatus.RISK_ANALYSIS_COMPLETE)

        logger.info(
            "Risk analysis completed",
            application_id=state["application_id"],
            score=overall_risk_analysis["score"],
            risk_level=overall_risk_analysis["details"]["overall_risk_level"]
        )

        return state

    except Exception as e:
        error_msg = f"Risk analysis failed: {str(e)}"
        logger.error("Risk analysis error", application_id=state["application_id"], error=str(e))

        state["errors"].append(error_msg)
        state["risk_analysis"] = {
            "status": "error",
            "score": 0.0,
            "confidence": 0.0,
            "summary": "Ошибка при анализе рисков",
            "details": {"error": str(e), "overall_risk_level": "critical"},
            "recommendations": ["Повторить анализ рисков"],
            "risks": [error_msg]
        }

        return state


async def analyze_financial_risks(form_data: Dict[str, Any]) -> Dict[str, Any]:
    """Анализ финансовых рисков"""

    result = {
        "risk_level": "medium",
        "risk_score": 0.5,
        "factors": [],
        "mitigation_strategies": []
    }

    requested_amount = form_data.get("requested_amount", 0)
    annual_revenue = form_data.get("annual_revenue", 0)
    net_profit = form_data.get("net_profit", 0)
    total_assets = form_data.get("total_assets", 0)
    debt_amount = form_data.get("debt_amount", 0)

    risk_factors = []

    # 1. Анализ соотношения кредита к обороту
    if annual_revenue > 0:
        credit_to_revenue_ratio = requested_amount / annual_revenue

        if credit_to_revenue_ratio > 10:
            risk_factors.append({
                "factor": "Критически высокое соотношение кредита к обороту",
                "value": credit_to_revenue_ratio,
                "risk_weight": 0.9,
                "description": f"Кредит превышает оборот в {credit_to_revenue_ratio:.1f} раз"
            })
        elif credit_to_revenue_ratio > 5:
            risk_factors.append({
                "factor": "Высокое соотношение кредита к обороту",
                "value": credit_to_revenue_ratio,
                "risk_weight": 0.7,
                "description": f"Кредит превышает оборот в {credit_to_revenue_ratio:.1f} раз"
            })
        elif credit_to_revenue_ratio > 2:
            risk_factors.append({
                "factor": "Умеренное соотношение кредита к обороту",
                "value": credit_to_revenue_ratio,
                "risk_weight": 0.4,
                "description": f"Кредит составляет {credit_to_revenue_ratio:.1f} годовых оборота"
            })
        else:
            risk_factors.append({
                "factor": "Приемлемое соотношение кредита к обороту",
                "value": credit_to_revenue_ratio,
                "risk_weight": 0.2,
                "description": f"Кредит составляет {credit_to_revenue_ratio:.1f} годовых оборота"
            })
    else:
        risk_factors.append({
            "factor": "Отсутствие данных о выручке",
            "value": 0,
            "risk_weight": 0.8,
            "description": "Невозможно оценить платежеспособность"
        })

    # 2. Анализ прибыльности
    if annual_revenue > 0 and net_profit is not None:
        profitability = net_profit / annual_revenue

        if profitability < -0.1:  # Убыток > 10%
            risk_factors.append({
                "factor": "Значительные убытки",
                "value": profitability,
                "risk_weight": 0.9,
                "description": f"Рентабельность: {profitability * 100:.1f}%"
            })
        elif profitability < 0:  # Убыточность
            risk_factors.append({
                "factor": "Убыточная деятельность",
                "value": profitability,
                "risk_weight": 0.7,
                "description": f"Рентабельность: {profitability * 100:.1f}%"
            })
        elif profitability < 0.05:  # Низкая прибыльность
            risk_factors.append({
                "factor": "Низкая прибыльность",
                "value": profitability,
                "risk_weight": 0.5,
                "description": f"Рентабельность: {profitability * 100:.1f}%"
            })
        else:
            risk_factors.append({
                "factor": "Приемлемая прибыльность",
                "value": profitability,
                "risk_weight": 0.2,
                "description": f"Рентабельность: {profitability * 100:.1f}%"
            })

    # 3. Анализ долговой нагрузки
    if total_assets > 0 and debt_amount is not None:
        debt_ratio = debt_amount / total_assets

        if debt_ratio > 0.8:
            risk_factors.append({
                "factor": "Критическая долговая нагрузка",
                "value": debt_ratio,
                "risk_weight": 0.9,
                "description": f"Долги составляют {debt_ratio * 100:.1f}% активов"
            })
        elif debt_ratio > 0.6:
            risk_factors.append({
                "factor": "Высокая долговая нагрузка",
                "value": debt_ratio,
                "risk_weight": 0.7,
                "description": f"Долги составляют {debt_ratio * 100:.1f}% активов"
            })
        elif debt_ratio > 0.4:
            risk_factors.append({
                "factor": "Умеренная долговая нагрузка",
                "value": debt_ratio,
                "risk_weight": 0.4,
                "description": f"Долги составляют {debt_ratio * 100:.1f}% активов"
            })
        else:
            risk_factors.append({
                "factor": "Низкая долговая нагрузка",
                "value": debt_ratio,
                "risk_weight": 0.2,
                "description": f"Долги составляют {debt_ratio * 100:.1f}% активов"
            })

    # 4. Размер компании (риск концентрации)
    if annual_revenue > 0:
        if annual_revenue < 50_000_000:  # Менее 50 млн
            risk_factors.append({
                "factor": "Малый размер компании",
                "value": annual_revenue,
                "risk_weight": 0.6,
                "description": "Повышенные риски из-за масштаба деятельности"
            })
        elif annual_revenue > 10_000_000_000:  # Более 10 млрд
            risk_factors.append({
                "factor": "Крупная компания",
                "value": annual_revenue,
                "risk_weight": 0.2,
                "description": "Низкие риски благодаря масштабу"
            })
        else:
            risk_factors.append({
                "factor": "Средний размер компании",
                "value": annual_revenue,
                "risk_weight": 0.3,
                "description": "Умеренные риски"
            })

    # Расчет общего финансового риска
    if risk_factors:
        weights_sum = sum(factor["risk_weight"] for factor in risk_factors)
        average_risk = weights_sum / len(risk_factors)

        result["risk_score"] = average_risk
        result["factors"] = risk_factors

        # Определение уровня риска
        if average_risk >= 0.8:
            result["risk_level"] = "critical"
            result["mitigation_strategies"] = [
                "Требуется дополнительное обеспечение",
                "Снижение суммы кредита",
                "Сокращение срока кредитования"
            ]
        elif average_risk >= 0.6:
            result["risk_level"] = "high"
            result["mitigation_strategies"] = [
                "Усиленный мониторинг финансового состояния",
                "Дополнительные гарантии",
                "Поэтапное кредитование"
            ]
        elif average_risk >= 0.4:
            result["risk_level"] = "medium"
            result["mitigation_strategies"] = [
                "Стандартный мониторинг",
                "Регулярная отчетность"
            ]
        else:
            result["risk_level"] = "low"
            result["mitigation_strategies"] = [
                "Базовые условия кредитования"
            ]

    return result


async def analyze_market_risks(form_data: Dict[str, Any], extracted_data: Dict[str, Any]) -> Dict[str, Any]:
    """Анализ рыночных рисков"""

    result = {
        "risk_level": "medium",
        "risk_score": 0.5,
        "factors": [],
        "mitigation_strategies": []
    }

    project_description = form_data.get("project_description", "").lower()
    requested_amount = form_data.get("requested_amount", 0)
    duration_months = form_data.get("project_duration_months", 0)

    risk_factors = []

    # 1. Отраслевые риски
    industry_risks = {
        "строительство": {
            "risk_score": 0.7,
            "description": "Высокая волатильность, зависимость от экономических циклов"
        },
        "нефтегаз": {
            "risk_score": 0.8,
            "description": "Зависимость от цен на нефть, геополитические риски"
        },
        "it": {
            "risk_score": 0.3,
            "description": "Быстрорастущая отрасль с умеренными рисками"
        },
        "производство": {
            "risk_score": 0.4,
            "description": "Стабильная отрасль с умеренными рисками"
        },
        "торговля": {
            "risk_score": 0.5,
            "description": "Зависимость от потребительского спроса"
        },
        "сельское хозяйство": {
            "risk_score": 0.6,
            "description": "Сезонность, погодные риски"
        },
        "транспорт": {
            "risk_score": 0.5,
            "description": "Зависимость от экономической активности"
        },
        "туризм": {
            "risk_score": 0.9,
            "description": "Высокая волатильность, внешние шоки"
        }
    }

    identified_industry = None
    for industry, risk_info in industry_risks.items():
        if industry in project_description:
            identified_industry = industry
            risk_factors.append({
                "factor": f"Отраслевой риск: {industry}",
                "value": risk_info["risk_score"],
                "risk_weight": risk_info["risk_score"],
                "description": risk_info["description"]
            })
            break

    if not identified_industry:
        risk_factors.append({
            "factor": "Неопределенная отрасль",
            "value": 0.6,
            "risk_weight": 0.6,
            "description": "Сложно оценить отраслевые риски"
        })

    # 2. Географические риски
    geographic_keywords = {
        "казахстан": 0.4,
        "россия": 0.6,
        "беларусь": 0.5,
        "узбекистан": 0.7,
        "кыргызстан": 0.7,
        "экспорт": 0.5,
        "импорт": 0.6
    }

    geographic_risk = 0.4  # Базовый риск
    geographic_factors = []

    for location, risk_score in geographic_keywords.items():
        if location in project_description:
            geographic_factors.append(location)
            geographic_risk = max(geographic_risk, risk_score)

    risk_factors.append({
        "factor": "Географический риск",
        "value": geographic_risk,
        "risk_weight": geographic_risk,
        "description": f"Регионы: {', '.join(geographic_factors) if geographic_factors else 'базовый'}"
    })

    # 3. Валютные риски
    currency_keywords = ["валют", "доллар", "евро", "экспорт", "импорт"]
    has_currency_exposure = any(keyword in project_description for keyword in currency_keywords)

    if has_currency_exposure:
        risk_factors.append({
            "factor": "Валютный риск",
            "value": 0.6,
            "risk_weight": 0.6,
            "description": "Проект подвержен валютным колебаниям"
        })

    # 4. Конкурентные риски
    competition_keywords = ["конкурент", "монополия", "рынок", "доля"]
    competition_mentioned = any(keyword in project_description for keyword in competition_keywords)

    if not competition_mentioned:
        risk_factors.append({
            "factor": "Неопределенность конкурентной среды",
            "value": 0.5,
            "risk_weight": 0.5,
            "description": "Отсутствует анализ конкуренции"
        })

    # 5. Размер проекта относительно рынка
    if requested_amount > 1_000_000_000:  # Более 1 млрд
        risk_factors.append({
            "factor": "Крупномасштабный проект",
            "value": 0.6,
            "risk_weight": 0.6,
            "description": "Повышенные рыночные риски из-за масштаба"
        })

    # 6. Временные риски
    if duration_months > 60:  # Более 5 лет
        risk_factors.append({
            "factor": "Долгосрочный проект",
            "value": 0.7,
            "risk_weight": 0.7,
            "description": "Высокая неопределенность рыночных условий"
        })
    elif duration_months > 36:  # 3-5 лет
        risk_factors.append({
            "factor": "Среднесрочный проект",
            "value": 0.4,
            "risk_weight": 0.4,
            "description": "Умеренная неопределенность"
        })

    # Расчет общего рыночного риска
    if risk_factors:
        average_risk = sum(factor["risk_weight"] for factor in risk_factors) / len(risk_factors)
        result["risk_score"] = average_risk
        result["factors"] = risk_factors

        if average_risk >= 0.7:
            result["risk_level"] = "high"
            result["mitigation_strategies"] = [
                "Диверсификация рынков сбыта",
                "Хеджирование валютных рисков",
                "Поэтапная реализация проекта"
            ]
        elif average_risk >= 0.5:
            result["risk_level"] = "medium"
            result["mitigation_strategies"] = [
                "Мониторинг рыночных условий",
                "Гибкая стратегия реализации"
            ]
        else:
            result["risk_level"] = "low"
            result["mitigation_strategies"] = [
                "Стандартный мониторинг рынка"
            ]

    return result


async def analyze_operational_risks(form_data: Dict[str, Any]) -> Dict[str, Any]:
    """Анализ операционных рисков"""

    result = {
        "risk_level": "medium",
        "risk_score": 0.5,
        "factors": [],
        "mitigation_strategies": []
    }

    project_description = form_data.get("project_description", "").lower()
    duration_months = form_data.get("project_duration_months", 0)
    requested_amount = form_data.get("requested_amount", 0)

    risk_factors = []

    # 1. Технологические риски
    tech_risk_keywords = {
        "инновац": 0.7,
        "новая технология": 0.8,
        "разработка": 0.6,
        "исследования": 0.7,
        "эксперимент": 0.8,
        "прототип": 0.9
    }

    max_tech_risk = 0.3  # Базовый технологический риск
    tech_factors = []

    for keyword, risk_score in tech_risk_keywords.items():
        if keyword in project_description:
            tech_factors.append(keyword)
            max_tech_risk = max(max_tech_risk, risk_score)

    risk_factors.append({
        "factor": "Технологический риск",
        "value": max_tech_risk,
        "risk_weight": max_tech_risk,
        "description": f"Факторы: {', '.join(tech_factors) if tech_factors else 'стандартные технологии'}"
    })

    # 2. Риски поставок и логистики
    supply_keywords = ["поставк", "логистик", "импорт", "сырье", "материал"]
    has_supply_exposure = any(keyword in project_description for keyword in supply_keywords)

    if has_supply_exposure:
        risk_factors.append({
            "factor": "Риски поставок",
            "value": 0.5,
            "risk_weight": 0.5,
            "description": "Зависимость от внешних поставщиков"
        })

    # 3. Кадровые риски
    hr_keywords = ["персонал", "специалист", "квалификация", "обучение"]
    has_hr_considerations = any(keyword in project_description for keyword in hr_keywords)

    if not has_hr_considerations and requested_amount > 100_000_000:
        risk_factors.append({
            "factor": "Кадровые риски",
            "value": 0.6,
            "risk_weight": 0.6,
            "description": "Отсутствует анализ кадрового обеспечения для крупного проекта"
        })

    # 4. Производственные риски
    production_keywords = ["производство", "оборудование", "мощности", "цех", "завод"]
    has_production = any(keyword in project_description for keyword in production_keywords)

    if has_production:
        equipment_keywords = ["новое оборудование", "модернизация", "реконструкция"]
        equipment_risk = any(keyword in project_description for keyword in equipment_keywords)

        if equipment_risk:
            risk_factors.append({
                "factor": "Риски модернизации производства",
                "value": 0.6,
                "risk_weight": 0.6,
                "description": "Риски связанные с внедрением нового оборудования"
            })
        else:
            risk_factors.append({
                "factor": "Производственные риски",
                "value": 0.4,
                "risk_weight": 0.4,
                "description": "Стандартные производственные риски"
            })

    # 5. Экологические и регулятивные риски
    env_keywords = ["экология", "лицензия", "разрешение", "сертификация", "стандарт"]
    has_regulatory_aspects = any(keyword in project_description for keyword in env_keywords)

    if not has_regulatory_aspects and requested_amount > 500_000_000:
        risk_factors.append({
            "factor": "Регулятивные риски",
            "value": 0.5,
            "risk_weight": 0.5,
            "description": "Не учтены требования регуляторов для крупного проекта"
        })

    # 6. Риски сроков реализации
    if duration_months <= 6:
        risk_factors.append({
            "factor": "Сжатые сроки реализации",
            "value": 0.7,
            "risk_weight": 0.7,
            "description": "Высокие риски несоблюдения графика"
        })
    elif duration_months >= 84:  # Более 7 лет
        risk_factors.append({
            "factor": "Чрезмерно долгие сроки",
            "value": 0.6,
            "risk_weight": 0.6,
            "description": "Риски изменения условий в процессе реализации"
        })
    else:
        risk_factors.append({
            "factor": "Приемлемые сроки реализации",
            "value": 0.3,
            "risk_weight": 0.3,
            "description": "Сроки соответствуют масштабу проекта"
        })

    # Расчет общего операционного риска
    if risk_factors:
        average_risk = sum(factor["risk_weight"] for factor in risk_factors) / len(risk_factors)
        result["risk_score"] = average_risk
        result["factors"] = risk_factors

        if average_risk >= 0.7:
            result["risk_level"] = "high"
            result["mitigation_strategies"] = [
                "Детальное планирование и контроль",
                "Резервирование ресурсов",
                "Поэтапная реализация с контрольными точками"
            ]
        elif average_risk >= 0.5:
            result["risk_level"] = "medium"
            result["mitigation_strategies"] = [
                "Регулярный мониторинг прогресса",
                "Планы реагирования на риски"
            ]
        else:
            result["risk_level"] = "low"
            result["mitigation_strategies"] = [
                "Стандартный операционный контроль"
            ]

    return result


async def analyze_management_risks(form_data: Dict[str, Any], extracted_data: Dict[str, Any]) -> Dict[str, Any]:
    """Анализ рисков менеджмента и корпоративного управления"""

    result = {
        "risk_level": "medium",
        "risk_score": 0.5,
        "factors": [],
        "mitigation_strategies": []
    }

    company_name = form_data.get("company_name", "")
    legal_form = form_data.get("legal_form", "").lower()
    contact_person = form_data.get("contact_person", "")

    risk_factors = []

    # 1. Тип организации и управление
    if "ип" in legal_form or "предприниматель" in legal_form:
        risk_factors.append({
            "factor": "Индивидуальное предпринимательство",
            "value": 0.7,
            "risk_weight": 0.7,
            "description": "Высокие риски из-за концентрации управления"
        })
    elif any(form in legal_form for form in ["ооо", "тоо"]):
        risk_factors.append({
            "factor": "Общество с ограниченной ответственностью",
            "value": 0.4,
            "risk_weight": 0.4,
            "description": "Умеренные риски корпоративного управления"
        })
    elif any(form in legal_form for form in ["ао", "пао", "зао"]):
        risk_factors.append({
            "factor": "Акционерное общество",
            "value": 0.3,
            "risk_weight": 0.3,
            "description": "Низкие риски благодаря структуре управления"
        })
    else:
        risk_factors.append({
            "factor": "Неопределенная организационная форма",
            "value": 0.6,
            "risk_weight": 0.6,
            "description": "Сложно оценить риски управления"
        })

    # 2. Анализ контактного лица
    if contact_person:
        name_parts = contact_person.strip().split()
        if len(name_parts) < 2:
            risk_factors.append({
                "factor": "Неполные данные контактного лица",
                "value": 0.5,
                "risk_weight": 0.5,
                "description": "Недостаточная информация о представителе"
            })
        else:
            risk_factors.append({
                "factor": "Представитель компании указан",
                "value": 0.2,
                "risk_weight": 0.2,
                "description": "Контактное лицо определено"
            })
    else:
        risk_factors.append({
            "factor": "Отсутствует контактное лицо",
            "value": 0.7,
            "risk_weight": 0.7,
            "description": "Не указан ответственный представитель"
        })

    # 3. Анализ на основе документов
    management_info_found = False

    for doc_path, doc_data in extracted_data.items():
        text = doc_data.get("text", "").lower()

        # Ищем информацию о руководстве
        management_keywords = [
            "директор", "руководитель", "управляющий", "президент",
            "генеральный", "исполнительный", "совет директоров"
        ]

        if any(keyword in text for keyword in management_keywords):
            management_info_found = True
            break

    if management_info_found:
        risk_factors.append({
            "factor": "Информация о руководстве найдена в документах",
            "value": 0.3,
            "risk_weight": 0.3,
            "description": "Документы содержат данные о менеджменте"
        })
    else:
        risk_factors.append({
            "factor": "Недостаток информации о руководстве",
            "value": 0.6,
            "risk_weight": 0.6,
            "description": "В документах отсутствует информация о менеджменте"
        })

    # 4. Возраст компании (по названию и документам)
    age_indicators = {
        "новая": 0.8,
        "молодая": 0.7,
        "стартап": 0.9,
        "недавно созданная": 0.8,
        "создана в": 0.5
    }

    text_to_analyze = f"{company_name} {form_data.get('project_description', '')}".lower()

    age_risk = 0.5  # Базовый риск
    for indicator, risk_score in age_indicators.items():
        if indicator in text_to_analyze:
            age_risk = max(age_risk, risk_score)
            break

    risk_factors.append({
        "factor": "Зрелость компании",
        "value": age_risk,
        "risk_weight": age_risk,
        "description": "Оценка на основе доступной информации"
    })

    # Расчет общего риска менеджмента
    if risk_factors:
        average_risk = sum(factor["risk_weight"] for factor in risk_factors) / len(risk_factors)
        result["risk_score"] = average_risk
        result["factors"] = risk_factors

        if average_risk >= 0.7:
            result["risk_level"] = "high"
            result["mitigation_strategies"] = [
                "Дополнительная проверка руководства",
                "Требование поручительства ключевых лиц",
                "Усиленный контроль за использованием средств"
            ]
        elif average_risk >= 0.5:
            result["risk_level"] = "medium"
            result["mitigation_strategies"] = [
                "Стандартная проверка менеджмента",
                "Регулярная отчетность"
            ]
        else:
            result["risk_level"] = "low"
            result["mitigation_strategies"] = [
                "Базовые требования к отчетности"
            ]

    return result


async def perform_llm_risk_analysis(
        form_data: Dict[str, Any],
        financial_risks: Dict[str, Any],
        market_risks: Dict[str, Any],
        operational_risks: Dict[str, Any]
) -> Dict[str, Any]:
    """LLM анализ комплексных рисков"""

    system_prompt = """Ты - эксперт по рискам и кредитному анализу.
    Проанализируй комплексные риски кредитного проекта на основе предварительных оценок.

    Обрати внимание на:
    1. Взаимосвязи между различными типами рисков
    2. Системные риски, которые могут усиливать друг друга
    3. Специфические риски, не учтенные в стандартном анализе
    4. Общую устойчивость проекта к различным сценариям

    Дай общую оценку риска от 0 до 1 (где 1 = максимальный риск) и опиши ключевые факторы.
    Ответь в формате JSON с полями: overall_risk, key_risks, risk_interactions, recommendations"""

    risk_summary = {
        "financial_risk": financial_risks.get("risk_level", "unknown"),
        "market_risk": market_risks.get("risk_level", "unknown"),
        "operational_risk": operational_risks.get("risk_level", "unknown"),
        "project_amount": form_data.get("requested_amount", 0),
        "project_duration": form_data.get("project_duration_months", 0),
        "project_description": form_data.get("project_description", "")[:500]
    }

    user_message = f"""
    Проанализируй общие риски проекта:

    Предварительные оценки рисков:
    - Финансовые риски: {financial_risks.get('risk_level', 'неизвестно')} (оценка: {financial_risks.get('risk_score', 0):.2f})
    - Рыночные риски: {market_risks.get('risk_level', 'неизвестно')} (оценка: {market_risks.get('risk_score', 0):.2f})
    - Операционные риски: {operational_risks.get('risk_level', 'неизвестно')} (оценка: {operational_risks.get('risk_score', 0):.2f})

    Параметры проекта:
    - Сумма: {form_data.get('requested_amount', 0):,} тенге
    - Срок: {form_data.get('project_duration_months', 0)} месяцев
    - Описание: {form_data.get('project_description', '')[:300]}...

    Проанализируй взаимосвязи рисков и дай рекомендации.
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
                    "overall_risk": 0.6,
                    "key_risks": ["Не удалось получить структурированный анализ"],
                    "risk_interactions": [],
                    "recommendations": []
                }
        else:
            # Простой анализ неструктурированного текста
            risk_score = 0.5
            if any(word in response_text.lower() for word in ["высокий", "критический", "опасн"]):
                risk_score = 0.8
            elif any(word in response_text.lower() for word in ["низкий", "минимальн", "приемлем"]):
                risk_score = 0.3

            llm_result = {
                "overall_risk": risk_score,
                "key_risks": [],
                "risk_interactions": [],
                "recommendations": [],
                "raw_analysis": response_text
            }

        return {
            "status": "success",
            "risk_score": llm_result.get("overall_risk", 0.6),
            "confidence": 0.7,
            "key_risks": llm_result.get("key_risks", []),
            "risk_interactions": llm_result.get("risk_interactions", []),
            "recommendations": llm_result.get("recommendations", []),
            "llm_analysis": response_text
        }

    except Exception as e:
        logger.error("LLM risk analysis failed", error=str(e))
        return {
            "status": "error",
            "risk_score": 0.7,  # Консервативная оценка при ошибке
            "confidence": 0.0,
            "key_risks": [f"Ошибка LLM анализа: {str(e)}"],
            "risk_interactions": [],
            "recommendations": [],
            "error": str(e)
        }


def combine_risk_results(
        financial_risks: Dict[str, Any],
        market_risks: Dict[str, Any],
        operational_risks: Dict[str, Any],
        management_risks: Dict[str, Any],
        llm_analysis: Dict[str, Any]
) -> Dict[str, Any]:
    """Объединение всех результатов анализа рисков"""

    # Веса различных типов рисков
    weights = {
        "financial": 0.35,
        "market": 0.25,
        "operational": 0.20,
        "management": 0.15,
        "llm_adjustment": 0.05
    }

    # Собираем оценки рисков
    risk_scores = {
        "financial": financial_risks.get("risk_score", 0.5),
        "market": market_risks.get("risk_score", 0.5),
        "operational": operational_risks.get("risk_score", 0.5),
        "management": management_risks.get("risk_score", 0.5),
        "llm": llm_analysis.get("risk_score", 0.5)
    }

    # Расчет взвешенной оценки
    weighted_score = (
            risk_scores["financial"] * weights["financial"] +
            risk_scores["market"] * weights["market"] +
            risk_scores["operational"] * weights["operational"] +
            risk_scores["management"] * weights["management"]
    )

    # Корректировка на основе LLM анализа
    llm_adjustment = (llm_analysis.get("risk_score", 0.5) - 0.5) * weights["llm_adjustment"]
    overall_score = max(0.0, min(1.0, weighted_score + llm_adjustment))

    # Определение общего уровня риска
    if overall_score >= 0.8:
        overall_risk_level = "critical"
        status = "rejected"
    elif overall_score >= 0.6:
        overall_risk_level = "high"
        status = "conditional"
    elif overall_score >= 0.4:
        overall_risk_level = "medium"
        status = "approved"
    else:
        overall_risk_level = "low"
        status = "approved"

    # Собираем все риски
    all_risks = []

    # Добавляем ключевые риски из каждой категории
    for risk_category, risk_data in [
        ("Финансовые", financial_risks),
        ("Рыночные", market_risks),
        ("Операционные", operational_risks),
        ("Управленческие", management_risks)
    ]:
        factors = risk_data.get("factors", [])
        high_risk_factors = [f for f in factors if f.get("risk_weight", 0) >= 0.6]

        for factor in high_risk_factors[:2]:  # Максимум 2 риска из каждой категории
            all_risks.append(f"{risk_category}: {factor['factor']}")

    # Добавляем LLM риски
    all_risks.extend(llm_analysis.get("key_risks", [])[:3])

    # Собираем рекомендации
    all_recommendations = []
    all_recommendations.extend(financial_risks.get("mitigation_strategies", []))
    all_recommendations.extend(market_risks.get("mitigation_strategies", []))
    all_recommendations.extend(operational_risks.get("mitigation_strategies", []))
    all_recommendations.extend(management_risks.get("mitigation_strategies", []))
    all_recommendations.extend(llm_analysis.get("recommendations", []))

    return {
        "status": status,
        "score": 1.0 - overall_score,  # Конвертируем в положительную оценку
        "confidence": llm_analysis.get("confidence", 0.7),
        "summary": f"Анализ рисков завершен. Общий уровень риска: {overall_risk_level}",
        "details": {
            "overall_risk_level": overall_risk_level,
            "overall_risk_score": overall_score,
            "financial_risk_score": risk_scores["financial"],
            "market_risk_score": risk_scores["market"],
            "operational_risk_score": risk_scores["operational"],
            "management_risk_score": risk_scores["management"],
            "component_analysis": {
                "financial_risks": financial_risks,
                "market_risks": market_risks,
                "operational_risks": operational_risks,
                "management_risks": management_risks,
                "llm_analysis": llm_analysis
            }
        },
        "recommendations": list(set(all_recommendations))[:8],  # Уникальные рекомендации, максимум 8
        "risks": all_risks[:10]  # Максимум 10 ключевых рисков
    }


def create_risk_reasoning(risk_analysis: Dict[str, Any]) -> str:
    """Создание текста рассуждений риск-менеджера"""

    score = risk_analysis.get("score", 0.0)
    details = risk_analysis.get("details", {})
    overall_risk_level = details.get("overall_risk_level", "unknown")
    risks = risk_analysis.get("risks", [])
    recommendations = risk_analysis.get("recommendations", [])

    reasoning_parts = []

    # Общая оценка
    risk_score = 1.0 - score  # Конвертируем обратно в риск
    if risk_score >= 0.8:
        reasoning_parts.append(f"🔴 КРИТИЧЕСКИЙ уровень риска: {risk_score:.2f}")
    elif risk_score >= 0.6:
        reasoning_parts.append(f"🟠 ВЫСОКИЙ уровень риска: {risk_score:.2f}")
    elif risk_score >= 0.4:
        reasoning_parts.append(f"🟡 СРЕДНИЙ уровень риска: {risk_score:.2f}")
    else:
        reasoning_parts.append(f"🟢 НИЗКИЙ уровень риска: {risk_score:.2f}")

    # Детализация по категориям
    reasoning_parts.append("\n📊 Анализ по категориям:")
    reasoning_parts.append(f"💰 Финансовые риски: {details.get('financial_risk_score', 0):.2f}")
    reasoning_parts.append(f"📈 Рыночные риски: {details.get('market_risk_score', 0):.2f}")
    reasoning_parts.append(f"⚙️ Операционные риски: {details.get('operational_risk_score', 0):.2f}")
    reasoning_parts.append(f"👥 Управленческие риски: {details.get('management_risk_score', 0):.2f}")

    # Ключевые риски
    if risks:
        reasoning_parts.append(f"\n⚠️ Ключевые риски ({len(risks)}):")
        reasoning_parts.extend([f"  • {risk}" for risk in risks[:5]])
        if len(risks) > 5:
            reasoning_parts.append(f"  • ... и еще {len(risks) - 5} рисков")

    # Рекомендации по снижению рисков
    if recommendations:
        reasoning_parts.append(f"\n💡 Рекомендации по снижению рисков ({len(recommendations)}):")
        reasoning_parts.extend([f"  • {rec}" for rec in recommendations[:4]])

    # Итоговое заключение
    if overall_risk_level == "critical":
        reasoning_parts.append("\n🔴 ЗАКЛЮЧЕНИЕ: Проект имеет критические риски, кредитование не рекомендуется")
    elif overall_risk_level == "high":
        reasoning_parts.append("\n🟠 ЗАКЛЮЧЕНИЕ: Высокие риски, требуются дополнительные гарантии и мониторинг")
    elif overall_risk_level == "medium":
        reasoning_parts.append("\n🟡 ЗАКЛЮЧЕНИЕ: Умеренные риски, кредитование возможно при стандартных условиях")
    else:
        reasoning_parts.append("\n🟢 ЗАКЛЮЧЕНИЕ: Низкие риски, проект приемлем для кредитования")

    return "\n".join(reasoning_parts)