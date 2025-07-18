"""
Узел проверки актуальности кредитных заявок
"""
import re
from typing import Dict, Any, List
from datetime import datetime

from ..state import CreditApplicationState, ProcessingStatus, add_agent_reasoning, update_processing_step
from ...services.llm_service import llm_service
from ...config.logging import logger


async def relevance_node(state: CreditApplicationState) -> CreditApplicationState:
    """
    Узел проверки актуальности проекта
    """
    logger.info("Starting relevance check", application_id=state["application_id"])

    # Обновляем статус
    state = update_processing_step(state, ProcessingStatus.RELEVANCE_CHECKING)

    try:
        # 1. Анализ рыночной актуальности
        market_relevance = await analyze_market_relevance(state["form_data"])

        # 2. Оценка инновационности проекта
        innovation_analysis = await analyze_project_innovation(state["form_data"])

        # 3. Экономический эффект и социальная значимость
        economic_impact = await analyze_economic_impact(state["form_data"])

        # 4. Соответствие приоритетам государственной политики
        policy_alignment = await analyze_policy_alignment(state["form_data"])

        # 5. LLM анализ актуальности в контексте
        llm_relevance_analysis = await perform_llm_relevance_analysis(
            state["form_data"],
            market_relevance,
            innovation_analysis,
            economic_impact,
            policy_alignment
        )

        # 6. Анализ устойчивости и ESG факторов
        sustainability_analysis = await analyze_sustainability(state["form_data"])

        # 7. Объединение результатов
        overall_relevance_analysis = combine_relevance_results(
            market_relevance,
            innovation_analysis,
            economic_impact,
            policy_alignment,
            sustainability_analysis,
            llm_relevance_analysis
        )

        # 8. Добавляем рассуждения агента
        reasoning = create_relevance_reasoning(overall_relevance_analysis)
        state = add_agent_reasoning(
            state,
            "relevance_checker",
            reasoning,
            confidence=overall_relevance_analysis["confidence"],
            metadata={
                "market_relevance": market_relevance["score"],
                "innovation_score": innovation_analysis["score"],
                "economic_impact": economic_impact["score"],
                "policy_alignment": policy_alignment["score"],
                "sustainability": sustainability_analysis["score"]
            }
        )

        # 9. Обновляем состояние
        state["relevance_analysis"] = overall_relevance_analysis
        state = update_processing_step(state, ProcessingStatus.RELEVANCE_CHECK_COMPLETE)

        logger.info(
            "Relevance check completed",
            application_id=state["application_id"],
            score=overall_relevance_analysis["score"],
            relevance_level=overall_relevance_analysis["details"]["relevance_level"]
        )

        return state

    except Exception as e:
        error_msg = f"Relevance check failed: {str(e)}"
        logger.error("Relevance check error", application_id=state["application_id"], error=str(e))

        state["errors"].append(error_msg)
        state["relevance_analysis"] = {
            "status": "error",
            "score": 0.0,
            "confidence": 0.0,
            "summary": "Ошибка при проверке актуальности",
            "details": {"error": str(e), "relevance_level": "unknown"},
            "recommendations": ["Повторить анализ актуальности"],
            "risks": [error_msg]
        }

        return state


async def analyze_market_relevance(form_data: Dict[str, Any]) -> Dict[str, Any]:
    """Анализ рыночной актуальности проекта"""

    result = {
        "score": 0.5,
        "factors": [],
        "market_trends": [],
        "competitive_position": "unknown"
    }

    project_description = form_data.get("project_description", "").lower()
    requested_amount = form_data.get("requested_amount", 0)

    # 1. Анализ трендовых направлений
    trending_sectors = {
        "цифровизация": {
            "score": 0.9,
            "keywords": ["цифров", "it", "автоматизация", "digitalization", "digital"],
            "description": "Высокоприоритетное направление цифровой трансформации"
        },
        "зеленые_технологии": {
            "score": 0.9,
            "keywords": ["экология", "возобновляемая энергия", "green", "эко", "солнечн", "ветр"],
            "description": "Экологически устойчивые технологии"
        },
        "импортозамещение": {
            "score": 0.8,
            "keywords": ["импортозамещение", "локализация", "отечественное", "местное производство"],
            "description": "Снижение зависимости от импорта"
        },
        "инновации": {
            "score": 0.8,
            "keywords": ["инновац", "нововведения", "r&d", "исследования", "разработка"],
            "description": "Инновационные решения и технологии"
        },
        "экспорт": {
            "score": 0.7,
            "keywords": ["экспорт", "международные рынки", "зарубежные поставки"],
            "description": "Развитие экспортного потенциала"
        },
        "агротех": {
            "score": 0.7,
            "keywords": ["агротехнологии", "сельское хозяйство", "agtech", "фермерство"],
            "description": "Современные технологии в сельском хозяйстве"
        },
        "логистика": {
            "score": 0.6,
            "keywords": ["логистика", "транспорт", "доставка", "складирование"],
            "description": "Развитие транспортно-логистической инфраструктуры"
        },
        "традиционные_отрасли": {
            "score": 0.4,
            "keywords": ["торговля", "розница", "услуги", "ремонт"],
            "description": "Традиционные направления деятельности"
        }
    }

    identified_sectors = []
    max_relevance_score = 0.3  # Базовая оценка

    for sector, info in trending_sectors.items():
        sector_matches = sum(1 for keyword in info["keywords"] if keyword in project_description)
        if sector_matches > 0:
            identified_sectors.append({
                "sector": sector,
                "relevance": info["score"],
                "matches": sector_matches,
                "description": info["description"]
            })
            max_relevance_score = max(max_relevance_score, info["score"])

    result["factors"].extend(identified_sectors)

    # 2. Анализ потребности рынка
    demand_indicators = {
        "растущий_спрос": ["растущий спрос", "увеличение потребности", "рост рынка", "expanding market"],
        "дефицит": ["дефицит", "нехватка", "shortage", "недостаток"],
        "новый_рынок": ["новый рынок", "неосвоенная ниша", "blue ocean", "новая ниша"],
        "конкуренция": ["высокая конкуренция", "насыщенный рынок", "много конкурентов"]
    }

    market_demand_score = 0.5
    demand_factors = []

    for indicator, keywords in demand_indicators.items():
        if any(keyword in project_description for keyword in keywords):
            if indicator in ["растущий_спрос", "дефицит", "новый_рынок"]:
                market_demand_score += 0.2
                demand_factors.append(f"Положительный индикатор: {indicator}")
            else:
                market_demand_score -= 0.1
                demand_factors.append(f"Вызов: {indicator}")

    result["market_trends"] = demand_factors

    # 3. Анализ целевой аудитории
    target_audience_indicators = {
        "b2b": ["предприятия", "компании", "b2b", "корпоративные клиенты"],
        "b2c": ["потребители", "население", "b2c", "частные лица"],
        "government": ["государственные", "муниципальные", "бюджетные организации"],
        "export": ["экспорт", "зарубежные", "международные"]
    }

    target_diversity = 0
    target_segments = []

    for segment, keywords in target_audience_indicators.items():
        if any(keyword in project_description for keyword in keywords):
            target_diversity += 1
            target_segments.append(segment)

    # Диверсификация целевой аудитории - положительный фактор
    if target_diversity >= 2:
        market_demand_score += 0.1
        result["factors"].append({
            "factor": "Диверсифицированная целевая аудитория",
            "score": 0.8,
            "description": f"Проект ориентирован на {len(target_segments)} сегментов"
        })

    # 4. Размер и потенциал рынка
    market_size_keywords = {
        "крупный_рынок": ["миллиарды", "крупнейший рынок", "массовый рынок"],
        "нишевый_рынок": ["нишевый", "специализированный", "узкий сегмент"],
        "локальный_рынок": ["местный рынок", "региональный", "локальный"]
    }

    market_size_score = 0.5
    for market_type, keywords in market_size_keywords.items():
        if any(keyword in project_description for keyword in keywords):
            if market_type == "крупный_рынок":
                market_size_score = 0.8
            elif market_type == "нишевый_рынок":
                market_size_score = 0.6
            else:  # локальный
                market_size_score = 0.4
            break

    # Общая оценка рыночной актуальности
    overall_market_score = (
            max_relevance_score * 0.4 +
            market_demand_score * 0.3 +
            market_size_score * 0.3
    )

    result["score"] = min(1.0, max(0.0, overall_market_score))

    # Определение конкурентной позиции
    if result["score"] >= 0.8:
        result["competitive_position"] = "strong"
    elif result["score"] >= 0.6:
        result["competitive_position"] = "moderate"
    else:
        result["competitive_position"] = "weak"

    return result


async def analyze_project_innovation(form_data: Dict[str, Any]) -> Dict[str, Any]:
    """Анализ инновационности проекта"""

    result = {
        "score": 0.4,  # Базовая оценка
        "innovation_level": "traditional",
        "innovation_factors": [],
        "technology_readiness": "unknown"
    }

    project_description = form_data.get("project_description", "").lower()

    # 1. Ключевые слова инноваций
    innovation_keywords = {
        "breakthrough": {
            "keywords": ["прорывные технологии", "революционный", "breakthrough", "disruptive"],
            "score": 1.0,
            "level": "breakthrough"
        },
        "advanced": {
            "keywords": ["передовые технологии", "advanced", "cutting-edge", "современные технологии"],
            "score": 0.8,
            "level": "advanced"
        },
        "incremental": {
            "keywords": ["улучшение", "модернизация", "оптимизация", "enhancement"],
            "score": 0.6,
            "level": "incremental"
        },
        "research": {
            "keywords": ["исследования", "разработка", "r&d", "ниокр", "research"],
            "score": 0.8,
            "level": "research-based"
        },
        "patent": {
            "keywords": ["патент", "интеллектуальная собственность", "ноу-хау", "patent"],
            "score": 0.9,
            "level": "patent-protected"
        }
    }

    max_innovation_score = 0.3
    innovation_factors = []

    for category, info in innovation_keywords.items():
        matches = sum(1 for keyword in info["keywords"] if keyword in project_description)
        if matches > 0:
            innovation_factors.append({
                "category": category,
                "matches": matches,
                "score": info["score"],
                "level": info["level"]
            })
            max_innovation_score = max(max_innovation_score, info["score"])

    result["innovation_factors"] = innovation_factors

    # 2. Технологическая готовность
    readiness_indicators = {
        "concept": ["концепция", "идея", "предварительные исследования"],
        "prototype": ["прототип", "опытный образец", "пилотный проект"],
        "testing": ["тестирование", "испытания", "валидация"],
        "production": ["готов к производству", "коммерциализация", "массовое производство"],
        "market": ["на рынке", "уже продается", "коммерческий успех"]
    }

    readiness_scores = {
        "concept": 0.3,
        "prototype": 0.5,
        "testing": 0.7,
        "production": 0.8,
        "market": 0.9
    }

    readiness_score = 0.4  # По умолчанию
    technology_readiness = "unknown"

    for stage, keywords in readiness_indicators.items():
        if any(keyword in project_description for keyword in keywords):
            readiness_score = readiness_scores[stage]
            technology_readiness = stage
            break

    result["technology_readiness"] = technology_readiness

    # 3. Цифровые технологии (дополнительный бонус)
    digital_keywords = [
        "искусственный интеллект", "машинное обучение", "big data",
        "blockchain", "iot", "cloud", "мобильные приложения",
        "автоматизация", "роботизация"
    ]

    digital_count = sum(1 for keyword in digital_keywords if keyword in project_description)
    digital_bonus = min(0.2, digital_count * 0.05)  # Максимум 0.2 бонуса

    # 4. Междисциплинарность
    disciplines = [
        "инженерия", "программирование", "биология", "химия", "физика",
        "экономика", "маркетинг", "дизайн", "экология"
    ]

    discipline_count = sum(1 for discipline in disciplines if discipline in project_description)
    interdisciplinary_bonus = min(0.15, (discipline_count - 1) * 0.05) if discipline_count > 1 else 0

    # Общая оценка инновационности
    overall_innovation_score = (
            max_innovation_score * 0.5 +
            readiness_score * 0.3 +
            digital_bonus +
            interdisciplinary_bonus
    )

    result["score"] = min(1.0, max(0.0, overall_innovation_score))

    # Определение уровня инновационности
    if result["score"] >= 0.8:
        result["innovation_level"] = "breakthrough"
    elif result["score"] >= 0.6:
        result["innovation_level"] = "advanced"
    elif result["score"] >= 0.4:
        result["innovation_level"] = "incremental"
    else:
        result["innovation_level"] = "traditional"

    return result


async def analyze_economic_impact(form_data: Dict[str, Any]) -> Dict[str, Any]:
    """Анализ экономического эффекта проекта"""

    result = {
        "score": 0.5,
        "impact_factors": [],
        "employment_effect": "unknown",
        "multiplier_effect": "low"
    }

    project_description = form_data.get("project_description", "").lower()
    requested_amount = form_data.get("requested_amount", 0)
    annual_revenue = form_data.get("annual_revenue", 0)

    impact_factors = []

    # 1. Создание рабочих мест
    employment_keywords = {
        "массовые_рабочие_места": ["сотни рабочих мест", "тысячи рабочих мест", "массовое трудоустройство"],
        "новые_рабочие_места": ["рабочие места", "трудоустройство", "занятость", "персонал"],
        "высококвалифицированные": ["высококвалифицированные", "специалисты", "инженеры", "программисты"]
    }

    employment_score = 0.3
    employment_effect = "minimal"

    for category, keywords in employment_keywords.items():
        if any(keyword in project_description for keyword in keywords):
            if category == "массовые_рабочие_места":
                employment_score = 0.9
                employment_effect = "significant"
            elif category == "новые_рабочие_места":
                employment_score = 0.6
                employment_effect = "moderate"
            elif category == "высококвалифицированные":
                employment_score += 0.2  # Бонус к существующей оценке
                employment_effect = "high-skilled"

    result["employment_effect"] = employment_effect
    impact_factors.append({
        "factor": "Влияние на занятость",
        "score": employment_score,
        "description": f"Эффект: {employment_effect}"
    })

    # 2. Мультипликативный эффект
    multiplier_keywords = {
        "высокий": ["смежные отрасли", "цепочки поставок", "кластерный эффект", "экосистема"],
        "средний": ["поставщики", "партнеры", "субподрядчики"],
        "экспорт": ["экспорт", "валютная выручка", "международные рынки"],
        "импортозамещение": ["импортозамещение", "снижение импорта", "локализация"]
    }

    multiplier_score = 0.3
    multiplier_effects = []

    for effect_type, keywords in multiplier_keywords.items():
        if any(keyword in project_description for keyword in keywords):
            multiplier_effects.append(effect_type)
            if effect_type == "высокий":
                multiplier_score = max(multiplier_score, 0.8)
            elif effect_type == "экспорт":
                multiplier_score = max(multiplier_score, 0.7)
            elif effect_type == "импортозамещение":
                multiplier_score = max(multiplier_score, 0.6)
            else:
                multiplier_score = max(multiplier_score, 0.5)

    if multiplier_score >= 0.7:
        result["multiplier_effect"] = "high"
    elif multiplier_score >= 0.5:
        result["multiplier_effect"] = "moderate"
    else:
        result["multiplier_effect"] = "low"

    impact_factors.append({
        "factor": "Мультипликативный эффект",
        "score": multiplier_score,
        "description": f"Эффекты: {', '.join(multiplier_effects) if multiplier_effects else 'ограниченный'}"
    })

    # 3. Региональное развитие
    regional_keywords = [
        "региональное развитие", "местное развитие", "развитие региона",
        "инфраструктура", "социальная значимость"
    ]

    regional_impact = any(keyword in project_description for keyword in regional_keywords)
    regional_score = 0.7 if regional_impact else 0.3

    impact_factors.append({
        "factor": "Региональное развитие",
        "score": regional_score,
        "description": "Значительное влияние на регион" if regional_impact else "Ограниченное влияние на регион"
    })

    # 4. Налоговые поступления (оценка по объему)
    if annual_revenue > 0:
        # Примерная оценка налогового эффекта
        estimated_tax_ratio = 0.15  # ~15% налоговая нагрузка
        tax_impact = annual_revenue * estimated_tax_ratio

        if tax_impact > 500_000_000:  # Более 500 млн налогов
            tax_score = 0.9
        elif tax_impact > 100_000_000:  # Более 100 млн
            tax_score = 0.7
        elif tax_impact > 10_000_000:  # Более 10 млн
            tax_score = 0.5
        else:
            tax_score = 0.3
    else:
        # Оценка по размеру проекта
        if requested_amount > 1_000_000_000:
            tax_score = 0.6
        elif requested_amount > 100_000_000:
            tax_score = 0.4
        else:
            tax_score = 0.2

    impact_factors.append({
        "factor": "Налоговые поступления",
        "score": tax_score,
        "description": f"Ожидаемый налоговый эффект на основе оборота"
    })

    # 5. Социальная значимость
    social_keywords = [
        "социально значимый", "общественная польза", "социальная ответственность",
        "образование", "здравоохранение", "экология", "доступность"
    ]

    social_impact = sum(1 for keyword in social_keywords if keyword in project_description)
    social_score = min(0.8, 0.3 + social_impact * 0.1)

    impact_factors.append({
        "factor": "Социальная значимость",
        "score": social_score,
        "description": f"Найдено {social_impact} социальных аспектов"
    })

    # Общая оценка экономического эффекта
    result["impact_factors"] = impact_factors
    overall_score = sum(factor["score"] for factor in impact_factors) / len(impact_factors)
    result["score"] = overall_score

    return result


async def analyze_policy_alignment(form_data: Dict[str, Any]) -> Dict[str, Any]:
    """Анализ соответствия приоритетам государственной политики"""

    result = {
        "score": 0.5,
        "policy_areas": [],
        "alignment_level": "moderate",
        "strategic_importance": "standard"
    }

    project_description = form_data.get("project_description", "").lower()

    # Приоритетные направления государственной политики
    policy_priorities = {
        "цифровизация": {
            "keywords": ["цифровизация", "digital", "цифровая экономика", "информационные технологии"],
            "score": 0.9,
            "importance": "critical"
        },
        "индустриализация": {
            "keywords": ["индустриализация", "производство", "промышленность", "manufacturing"],
            "score": 0.8,
            "importance": "high"
        },
        "инновации": {
            "keywords": ["инновации", "r&d", "исследования", "стартап", "технопарк"],
            "score": 0.8,
            "importance": "high"
        },
        "экология": {
            "keywords": ["экология", "зеленая экономика", "возобновляемая энергия", "устойчивое развитие"],
            "score": 0.8,
            "importance": "high"
        },
        "импортозамещение": {
            "keywords": ["импортозамещение", "локализация", "отечественное производство"],
            "score": 0.7,
            "importance": "medium"
        },
        "экспорт": {
            "keywords": ["экспорт", "экспортный потенциал", "зарубежные рынки"],
            "score": 0.7,
            "importance": "medium"
        },
        "туризм": {
            "keywords": ["туризм", "гостеприимство", "культурное наследие"],
            "score": 0.6,
            "importance": "medium"
        },
        "агропром": {
            "keywords": ["сельское хозяйство", "агропромышленность", "продовольственная безопасность"],
            "score": 0.7,
            "importance": "medium"
        },
        "образование": {
            "keywords": ["образование", "человеческий капитал", "навыки", "квалификация"],
            "score": 0.8,
            "importance": "high"
        },
        "здравоохранение": {
            "keywords": ["здравоохранение", "медицина", "фармацевтика", "биотехнологии"],
            "score": 0.8,
            "importance": "high"
        }
    }

    aligned_areas = []
    max_policy_score = 0.3
    strategic_indicators = []

    for area, info in policy_priorities.items():
        matches = sum(1 for keyword in info["keywords"] if keyword in project_description)
        if matches > 0:
            aligned_areas.append({
                "area": area,
                "matches": matches,
                "score": info["score"],
                "importance": info["importance"]
            })
            max_policy_score = max(max_policy_score, info["score"])

            if info["importance"] in ["critical", "high"]:
                strategic_indicators.append(area)

    result["policy_areas"] = aligned_areas

    # Определение стратегической важности
    if len(strategic_indicators) >= 2:
        result["strategic_importance"] = "critical"
        strategic_bonus = 0.2
    elif len(strategic_indicators) == 1:
        result["strategic_importance"] = "high"
        strategic_bonus = 0.1
    else:
        result["strategic_importance"] = "standard"
        strategic_bonus = 0.0

    # Специальные программы государственного развития
    government_programs = {
        "индустрия_4_0": ["индустрия 4.0", "четвертая промышленная революция", "умное производство"],
        "цифровой_казахстан": ["цифровой казахстан", "digital kazakhstan"],
        "зеленая_экономика": ["зеленая экономика", "green economy", "устойчивое развитие"],
        "нурлы_жол": ["нурлы жол", "инфраструктурное развитие", "транспортная инфраструктура"]
    }

    program_alignment = 0
    aligned_programs = []

    for program, keywords in government_programs.items():
        if any(keyword in project_description for keyword in keywords):
            program_alignment += 0.1
            aligned_programs.append(program)

    # Общая оценка соответствия политике
    total_score = min(1.0, max_policy_score + strategic_bonus + program_alignment)
    result["score"] = total_score

    # Определение уровня соответствия
    if total_score >= 0.8:
        result["alignment_level"] = "high"
    elif total_score >= 0.6:
        result["alignment_level"] = "moderate"
    else:
        result["alignment_level"] = "low"

    if aligned_programs:
        result["government_programs"] = aligned_programs

    return result


async def analyze_sustainability(form_data: Dict[str, Any]) -> Dict[str, Any]:
    """Анализ устойчивости и ESG факторов"""

    result = {
        "score": 0.5,
        "esg_factors": {
            "environmental": 0.5,
            "social": 0.5,
            "governance": 0.5
        },
        "sustainability_level": "moderate"
    }

    project_description = form_data.get("project_description", "").lower()

    # Environmental факторы
    environmental_keywords = {
        "positive": ["экология", "зеленые технологии", "возобновляемая энергия", "энергоэффективность",
                     "переработка", "снижение выбросов", "устойчивое развитие"],
        "negative": ["вредные выбросы", "загрязнение", "токсичные отходы", "экологический ущерб"]
    }

    env_score = 0.5
    env_positive = sum(1 for keyword in environmental_keywords["positive"] if keyword in project_description)
    env_negative = sum(1 for keyword in environmental_keywords["negative"] if keyword in project_description)

    env_score += env_positive * 0.1 - env_negative * 0.2
    result["esg_factors"]["environmental"] = max(0.0, min(1.0, env_score))

    # Social факторы
    social_keywords = {
        "positive": ["рабочие места", "социальная ответственность", "образование", "здравоохранение",
                     "инклюзивность", "равенство", "местное сообщество"],
        "negative": ["сокращение персонала", "социальная напряженность"]
    }

    social_score = 0.5
    social_positive = sum(1 for keyword in social_keywords["positive"] if keyword in project_description)
    social_negative = sum(1 for keyword in social_keywords["negative"] if keyword in project_description)

    social_score += social_positive * 0.1 - social_negative * 0.2
    result["esg_factors"]["social"] = max(0.0, min(1.0, social_score))

    # Governance факторы
    governance_keywords = {
        "positive": ["прозрачность", "отчетность", "корпоративное управление", "этика", "compliance"],
        "neutral": ["управление", "менеджмент", "процедуры"]
    }

    governance_score = 0.5
    gov_positive = sum(1 for keyword in governance_keywords["positive"] if keyword in project_description)
    gov_neutral = sum(1 for keyword in governance_keywords["neutral"] if keyword in project_description)

    governance_score += gov_positive * 0.15 + gov_neutral * 0.05
    result["esg_factors"]["governance"] = max(0.0, min(1.0, governance_score))

    # Общая оценка устойчивости
    overall_sustainability = (
            result["esg_factors"]["environmental"] * 0.4 +
            result["esg_factors"]["social"] * 0.35 +
            result["esg_factors"]["governance"] * 0.25
    )

    result["score"] = overall_sustainability

    # Определение уровня устойчивости
    if overall_sustainability >= 0.7:
        result["sustainability_level"] = "high"
    elif overall_sustainability >= 0.5:
        result["sustainability_level"] = "moderate"
    else:
        result["sustainability_level"] = "low"

    return result


async def perform_llm_relevance_analysis(
        form_data: Dict[str, Any],
        market_relevance: Dict[str, Any],
        innovation_analysis: Dict[str, Any],
        economic_impact: Dict[str, Any],
        policy_alignment: Dict[str, Any]
) -> Dict[str, Any]:
    """LLM анализ актуальности проекта"""

    system_prompt = """Ты - эксперт по стратегическому планированию и инновационному развитию.
    Проанализируй актуальность и перспективность проекта в контексте текущих трендов и потребностей рынка.

    Обрати внимание на:
    1. Соответствие современным трендам и потребностям
    2. Долгосрочную перспективность направления
    3. Потенциал влияния на экономику и общество
    4. Риски устаревания или снижения актуальности

    Дай оценку актуальности от 0 до 1 и опиши ключевые факторы.
    Ответь в формате JSON с полями: relevance_score, future_prospects, key_trends, risks, recommendations"""

    analysis_summary = {
        "market_relevance": market_relevance.get("score", 0.5),
        "innovation_level": innovation_analysis.get("score", 0.5),
        "economic_impact": economic_impact.get("score", 0.5),
        "policy_alignment": policy_alignment.get("score", 0.5),
        "project_description": form_data.get("project_description", "")[:800]
    }

    user_message = f"""
    Проанализируй актуальность проекта:

    Предварительные оценки:
    - Рыночная актуальность: {market_relevance.get('score', 0):.2f}
    - Инновационность: {innovation_analysis.get('score', 0):.2f}
    - Экономический эффект: {economic_impact.get('score', 0):.2f}
    - Соответствие политике: {policy_alignment.get('score', 0):.2f}

    Описание проекта:
    {form_data.get('project_description', '')[:600]}

    Оцени долгосрочную актуальность и перспективы проекта.
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
                    "relevance_score": 0.6,
                    "future_prospects": "moderate",
                    "key_trends": [],
                    "risks": ["Не удалось получить структурированный анализ"],
                    "recommendations": []
                }
        else:
            # Анализ неструктурированного текста
            score = 0.6
            if any(word in response_text.lower() for word in ["высокая актуальность", "перспективн", "востребован"]):
                score = 0.8
            elif any(word in response_text.lower() for word in ["низкая актуальность", "устарев", "неперспективн"]):
                score = 0.3

            llm_result = {
                "relevance_score": score,
                "future_prospects": "moderate",
                "key_trends": [],
                "risks": [],
                "recommendations": [],
                "raw_analysis": response_text
            }

        return {
            "status": "success",
            "score": llm_result.get("relevance_score", 0.6),
            "confidence": 0.7,
            "future_prospects": llm_result.get("future_prospects", "moderate"),
            "key_trends": llm_result.get("key_trends", []),
            "risks": llm_result.get("risks", []),
            "recommendations": llm_result.get("recommendations", []),
            "llm_analysis": response_text
        }

    except Exception as e:
        logger.error("LLM relevance analysis failed", error=str(e))
        return {
            "status": "error",
            "score": 0.5,
            "confidence": 0.0,
            "future_prospects": "unknown",
            "key_trends": [],
            "risks": [f"Ошибка LLM анализа: {str(e)}"],
            "recommendations": [],
            "error": str(e)
        }


def combine_relevance_results(
        market_relevance: Dict[str, Any],
        innovation_analysis: Dict[str, Any],
        economic_impact: Dict[str, Any],
        policy_alignment: Dict[str, Any],
        sustainability_analysis: Dict[str, Any],
        llm_analysis: Dict[str, Any]
) -> Dict[str, Any]:
    """Объединение всех результатов анализа актуальности"""

    # Веса компонентов
    weights = {
        "market": 0.25,
        "innovation": 0.25,
        "economic": 0.20,
        "policy": 0.15,
        "sustainability": 0.10,
        "llm_adjustment": 0.05
    }

    # Расчет взвешенной оценки
    component_scores = {
        "market": market_relevance.get("score", 0.5),
        "innovation": innovation_analysis.get("score", 0.5),
        "economic": economic_impact.get("score", 0.5),
        "policy": policy_alignment.get("score", 0.5),
        "sustainability": sustainability_analysis.get("score", 0.5),
        "llm": llm_analysis.get("score", 0.5)
    }

    weighted_score = (
            component_scores["market"] * weights["market"] +
            component_scores["innovation"] * weights["innovation"] +
            component_scores["economic"] * weights["economic"] +
            component_scores["policy"] * weights["policy"] +
            component_scores["sustainability"] * weights["sustainability"]
    )

    # Корректировка на основе LLM анализа
    llm_adjustment = (component_scores["llm"] - 0.5) * weights["llm_adjustment"]
    overall_score = max(0.0, min(1.0, weighted_score + llm_adjustment))

    # Определение уровня актуальности
    if overall_score >= 0.8:
        relevance_level = "high"
        status = "approved"
    elif overall_score >= 0.6:
        relevance_level = "moderate"
        status = "approved"
    elif overall_score >= 0.4:
        relevance_level = "low"
        status = "conditional"
    else:
        relevance_level = "very_low"
        status = "rejected"

    # Собираем ключевые выводы
    key_strengths = []
    key_weaknesses = []

    if component_scores["market"] >= 0.7:
        key_strengths.append("Высокая рыночная актуальность")
    elif component_scores["market"] <= 0.4:
        key_weaknesses.append("Низкая рыночная актуальность")

    if component_scores["innovation"] >= 0.7:
        key_strengths.append("Инновационность проекта")
    elif component_scores["innovation"] <= 0.4:
        key_weaknesses.append("Низкий уровень инноваций")

    if component_scores["policy"] >= 0.7:
        key_strengths.append("Соответствие государственным приоритетам")
    elif component_scores["policy"] <= 0.4:
        key_weaknesses.append("Слабое соответствие политике развития")

    # Собираем все рекомендации
    all_recommendations = []
    all_recommendations.extend(llm_analysis.get("recommendations", []))

    if component_scores["market"] < 0.5:
        all_recommendations.append("Провести дополнительное исследование рынка")

    if component_scores["innovation"] < 0.5:
        all_recommendations.append("Усилить инновационную составляющую проекта")

    if component_scores["sustainability"] < 0.5:
        all_recommendations.append("Учесть ESG факторы и устойчивое развитие")

    return {
        "status": status,
        "score": overall_score,
        "confidence": llm_analysis.get("confidence", 0.7),
        "summary": f"Анализ актуальности завершен. Уровень актуальности: {relevance_level}",
        "details": {
            "relevance_level": relevance_level,
            "market_relevance_score": component_scores["market"],
            "innovation_score": component_scores["innovation"],
            "economic_impact_score": component_scores["economic"],
            "policy_alignment_score": component_scores["policy"],
            "sustainability_score": component_scores["sustainability"],
            "component_analysis": {
                "market_relevance": market_relevance,
                "innovation_analysis": innovation_analysis,
                "economic_impact": economic_impact,
                "policy_alignment": policy_alignment,
                "sustainability_analysis": sustainability_analysis,
                "llm_analysis": llm_analysis
            },
            "key_strengths": key_strengths,
            "key_weaknesses": key_weaknesses
        },
        "recommendations": list(set(all_recommendations))[:6],
        "risks": llm_analysis.get("risks", [])[:5]
    }


def create_relevance_reasoning(relevance_analysis: Dict[str, Any]) -> str:
    """Создание текста рассуждений агента актуальности"""

    score = relevance_analysis.get("score", 0.0)
    details = relevance_analysis.get("details", {})
    relevance_level = details.get("relevance_level", "unknown")
    key_strengths = details.get("key_strengths", [])
    key_weaknesses = details.get("key_weaknesses", [])
    recommendations = relevance_analysis.get("recommendations", [])

    reasoning_parts = []

    # Общая оценка
    if score >= 0.8:
        reasoning_parts.append(f"🌟 ВЫСОКАЯ актуальность проекта: {score:.2f}")
    elif score >= 0.6:
        reasoning_parts.append(f"✅ УМЕРЕННАЯ актуальность проекта: {score:.2f}")
    elif score >= 0.4:
        reasoning_parts.append(f"⚠️ НИЗКАЯ актуальность проекта: {score:.2f}")
    else:
        reasoning_parts.append(f"❌ ОЧЕНЬ НИЗКАЯ актуальность проекта: {score:.2f}")

    # Детализация по компонентам
    reasoning_parts.append("\n📊 Анализ компонентов актуальности:")
    reasoning_parts.append(f"📈 Рыночная актуальность: {details.get('market_relevance_score', 0):.2f}")
    reasoning_parts.append(f"💡 Инновационность: {details.get('innovation_score', 0):.2f}")
    reasoning_parts.append(f"💰 Экономический эффект: {details.get('economic_impact_score', 0):.2f}")
    reasoning_parts.append(f"🏛️ Соответствие политике: {details.get('policy_alignment_score', 0):.2f}")
    reasoning_parts.append(f"🌱 Устойчивость (ESG): {details.get('sustainability_score', 0):.2f}")

    # Сильные стороны
    if key_strengths:
        reasoning_parts.append(f"\n✅ Сильные стороны ({len(key_strengths)}):")
        reasoning_parts.extend([f"  • {strength}" for strength in key_strengths])

    # Слабые стороны
    if key_weaknesses:
        reasoning_parts.append(f"\n⚠️ Области для улучшения ({len(key_weaknesses)}):")
        reasoning_parts.extend([f"  • {weakness}" for weakness in key_weaknesses])

    # Рекомендации
    if recommendations:
        reasoning_parts.append(f"\n💡 Рекомендации ({len(recommendations)}):")
        reasoning_parts.extend([f"  • {rec}" for rec in recommendations[:4]])

    # Итоговое заключение
    if relevance_level == "high":
        reasoning_parts.append("\n🌟 ЗАКЛЮЧЕНИЕ: Проект высоко актуален и перспективен")
    elif relevance_level == "moderate":
        reasoning_parts.append("\n✅ ЗАКЛЮЧЕНИЕ: Проект актуален, рекомендуется к реализации")
    elif relevance_level == "low":
        reasoning_parts.append("\n⚠️ ЗАКЛЮЧЕНИЕ: Актуальность проекта под вопросом, требуется доработка")
    else:
        reasoning_parts.append("\n❌ ЗАКЛЮЧЕНИЕ: Проект не соответствует текущим приоритетам развития")

    return "\n".join(reasoning_parts)