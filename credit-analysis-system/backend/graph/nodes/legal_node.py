"""
Узел юридической проверки кредитных заявок
"""
import re
from typing import Dict, Any, List
from datetime import datetime, timedelta

from ..state import CreditApplicationState, ProcessingStatus, add_agent_reasoning, update_processing_step
from ..tools.validation_tools import validate_inn, validate_bin_kz
from ...services.llm_service import llm_service
from ...config.logging import logger


async def legal_node(state: CreditApplicationState) -> CreditApplicationState:
    """
    Узел юридической проверки заявки
    """
    logger.info("Starting legal check", application_id=state["application_id"])

    # Обновляем статус
    state = update_processing_step(state, ProcessingStatus.LEGAL_CHECKING)

    try:
        # 1. Проверка юридических данных компании
        company_legal_check = await check_company_legal_data(state["form_data"])

        # 2. Анализ документов на соответствие законодательству
        documents_legal_check = await analyze_legal_documents(
            state.get("validation_result", {}).get("extracted_data", {})
        )

        # 3. LLM анализ юридических рисков
        llm_legal_analysis = await perform_llm_legal_analysis(
            state["form_data"],
            company_legal_check,
            documents_legal_check
        )

        # 4. Проверка соответствия требованиям фонда
        compliance_check = await check_fund_requirements_compliance(state["form_data"])

        # 5. Объединение результатов
        overall_legal_analysis = combine_legal_results(
            company_legal_check,
            documents_legal_check,
            llm_legal_analysis,
            compliance_check
        )

        # 6. Добавляем рассуждения агента
        reasoning = create_legal_reasoning(overall_legal_analysis)
        state = add_agent_reasoning(
            state,
            "legal_checker",
            reasoning,
            confidence=overall_legal_analysis["confidence"],
            metadata={
                "company_check_score": company_legal_check["score"],
                "documents_check_score": documents_legal_check["score"],
                "compliance_score": compliance_check["score"],
                "total_risks": len(overall_legal_analysis["risks"])
            }
        )

        # 7. Обновляем состояние
        state["legal_analysis"] = overall_legal_analysis
        state = update_processing_step(state, ProcessingStatus.LEGAL_CHECK_COMPLETE)

        logger.info(
            "Legal check completed",
            application_id=state["application_id"],
            score=overall_legal_analysis["score"],
            risks_count=len(overall_legal_analysis["risks"])
        )

        return state

    except Exception as e:
        error_msg = f"Legal check failed: {str(e)}"
        logger.error("Legal check error", application_id=state["application_id"], error=str(e))

        state["errors"].append(error_msg)
        state["legal_analysis"] = {
            "status": "error",
            "score": 0.0,
            "confidence": 0.0,
            "summary": "Ошибка при юридической проверке",
            "details": {"error": str(e)},
            "recommendations": [],
            "risks": [error_msg]
        }

        return state


async def check_company_legal_data(form_data: Dict[str, Any]) -> Dict[str, Any]:
    """Проверка юридических данных компании"""

    result = {
        "score": 0.0,
        "issues": [],
        "positive_aspects": [],
        "checks_performed": []
    }

    score_factors = []

    # Проверка ИНН/БИН
    tax_number = form_data.get("tax_number", "")
    if tax_number:
        # Определяем тип номера и валидируем
        clean_number = re.sub(r'[^\d]', '', tax_number)

        if len(clean_number) == 12 and clean_number.startswith(('0', '1', '2')):
            # Похоже на БИН Казахстана
            bin_result = {"is_valid": True, "errors": [], "warnings": []}
            bin_result = validate_bin_kz(tax_number, bin_result)

            if bin_result["is_valid"]:
                result["positive_aspects"].append("БИН прошел валидацию")
                score_factors.append(1.0)
            else:
                result["issues"].extend(bin_result["errors"])
                score_factors.append(0.2)

            result["checks_performed"].append("БИН валидация")

        elif len(clean_number) in [10, 12]:
            # Похоже на ИНН
            inn_result = {"is_valid": True, "errors": [], "warnings": []}
            inn_result = validate_inn(tax_number, inn_result)

            if inn_result["is_valid"]:
                result["positive_aspects"].append("ИНН прошел валидацию")
                score_factors.append(1.0)
            else:
                result["issues"].extend(inn_result["errors"])
                score_factors.append(0.3)

            result["checks_performed"].append("ИНН валидация")
        else:
            result["issues"].append("Некорректный формат налогового номера")
            score_factors.append(0.1)
    else:
        result["issues"].append("Отсутствует налоговый номер")
        score_factors.append(0.0)

    # Проверка названия компании
    company_name = form_data.get("company_name", "")
    if company_name:
        name_check = analyze_company_name(company_name)
        result["positive_aspects"].extend(name_check["positive"])
        result["issues"].extend(name_check["issues"])
        score_factors.append(name_check["score"])
        result["checks_performed"].append("Анализ названия")

    # Проверка организационно-правовой формы
    legal_form = form_data.get("legal_form", "")
    if legal_form:
        form_check = validate_legal_form(legal_form)
        result["positive_aspects"].extend(form_check["positive"])
        result["issues"].extend(form_check["issues"])
        score_factors.append(form_check["score"])
        result["checks_performed"].append("Проверка правовой формы")

    # Проверка адреса
    address = form_data.get("registration_address", "")
    if address:
        address_check = validate_legal_address(address)
        result["positive_aspects"].extend(address_check["positive"])
        result["issues"].extend(address_check["issues"])
        score_factors.append(address_check["score"])
        result["checks_performed"].append("Проверка адреса")

    # Расчет общей оценки
    if score_factors:
        result["score"] = sum(score_factors) / len(score_factors)

    return result


def analyze_company_name(company_name: str) -> Dict[str, Any]:
    """Анализ названия компании"""

    result = {
        "score": 0.7,  # Базовая оценка
        "positive": [],
        "issues": []
    }

    name_lower = company_name.lower()

    # Проверяем наличие правовой формы в названии
    legal_forms = ["ооо", "тоо", "ао", "зао", "оао", "ип", "пао"]
    has_legal_form = any(form in name_lower for form in legal_forms)

    if has_legal_form:
        result["positive"].append("Название содержит организационно-правовую форму")
        result["score"] += 0.1
    else:
        result["issues"].append("Название не содержит организационно-правовую форму")
        result["score"] -= 0.2

    # Проверяем длину названия
    if len(company_name) < 5:
        result["issues"].append("Слишком короткое название компании")
        result["score"] -= 0.2
    elif len(company_name) > 100:
        result["issues"].append("Слишком длинное название компании")
        result["score"] -= 0.1

    # Проверяем на подозрительные символы
    suspicious_chars = ['@', '#', '$', '%', '&', '*']
    if any(char in company_name for char in suspicious_chars):
        result["issues"].append("Название содержит подозрительные символы")
        result["score"] -= 0.3

    # Проверяем на отраслевые маркеры
    industry_keywords = [
        "производство", "строительство", "торговля", "услуги", "технологии",
        "инвест", "девелопмент", "консалтинг", "логистика", "транспорт"
    ]

    has_industry_marker = any(keyword in name_lower for keyword in industry_keywords)
    if has_industry_marker:
        result["positive"].append("Название отражает сферу деятельности")
        result["score"] += 0.1

    return result


def validate_legal_form(legal_form: str) -> Dict[str, Any]:
    """Валидация организационно-правовой формы"""

    result = {
        "score": 0.5,
        "positive": [],
        "issues": []
    }

    # Допустимые формы для разных юрисдикций
    valid_forms = {
        # Казахстан
        "тоо": "Товарищество с ограниченной ответственностью",
        "ао": "Акционерное общество",
        "уп": "Учреждение предпринимателя",
        "гу": "Государственное учреждение",

        # Россия
        "ооо": "Общество с ограниченной ответственностью",
        "пао": "Публичное акционерное общество",
        "зао": "Закрытое акционерное общество",
        "ип": "Индивидуальный предприниматель",

        # Общие
        "оао": "Открытое акционерное общество",
    }

    form_lower = legal_form.lower().strip()

    if form_lower in valid_forms:
        result["positive"].append(f"Допустимая правовая форма: {valid_forms[form_lower]}")
        result["score"] = 1.0
    else:
        # Проверяем частичные совпадения
        partial_match = False
        for valid_form, description in valid_forms.items():
            if valid_form in form_lower or form_lower in valid_form:
                result["positive"].append(f"Возможное соответствие: {description}")
                result["score"] = 0.8
                partial_match = True
                break

        if not partial_match:
            result["issues"].append(f"Неизвестная правовая форма: {legal_form}")
            result["score"] = 0.2

    return result


def validate_legal_address(address: str) -> Dict[str, Any]:
    """Валидация юридического адреса"""

    result = {
        "score": 0.7,
        "positive": [],
        "issues": []
    }

    address_lower = address.lower()

    # Проверяем наличие ключевых элементов адреса
    required_elements = {
        "город": ["г.", "город", "г ", "city"],
        "улица": ["ул.", "улица", "пр.", "проспект", "бул.", "бульвар"],
        "дом": ["д.", "дом", "№", "house"],
    }

    found_elements = 0
    for element_type, variants in required_elements.items():
        if any(variant in address_lower for variant in variants):
            found_elements += 1
            result["positive"].append(f"Найден элемент адреса: {element_type}")

    if found_elements >= 2:
        result["score"] += 0.2
    elif found_elements == 1:
        result["issues"].append("Неполный адрес - отсутствуют некоторые элементы")
        result["score"] -= 0.1
    else:
        result["issues"].append("Адрес не содержит стандартных элементов")
        result["score"] -= 0.3

    # Проверяем длину адреса
    if len(address) < 20:
        result["issues"].append("Слишком короткий адрес")
        result["score"] -= 0.2

    # Проверяем наличие цифр (номера домов, квартир)
    if not re.search(r'\d', address):
        result["issues"].append("Адрес не содержит номеров")
        result["score"] -= 0.2

    return result


async def analyze_legal_documents(extracted_data: Dict[str, Any]) -> Dict[str, Any]:
    """Анализ юридических документов"""

    result = {
        "score": 0.6,
        "document_analysis": {},
        "missing_documents": [],
        "compliance_issues": []
    }

    # Ожидаемые типы документов
    expected_docs = {
        "charter": "Устав организации",
        "financial_report": "Финансовая отчетность",
        "bank_statement": "Справка из банка",
        "license": "Лицензии (если требуются)"
    }

    # Анализируем каждый документ
    found_doc_types = set()

    for doc_path, doc_data in extracted_data.items():
        text = doc_data.get("text", "")
        doc_type = determine_document_type(text)

        if doc_type != "unknown":
            found_doc_types.add(doc_type)

            # Анализируем содержимое в зависимости от типа
            analysis = analyze_document_content(text, doc_type)
            result["document_analysis"][doc_path] = {
                "type": doc_type,
                "analysis": analysis
            }

            if analysis["score"] < 0.5:
                result["compliance_issues"].append(
                    f"Проблемы в документе {doc_path}: {analysis['issues']}"
                )

    # Проверяем комплектность
    for doc_type, description in expected_docs.items():
        if doc_type not in found_doc_types:
            result["missing_documents"].append(description)

    # Корректируем оценку на основе комплектности
    completeness_ratio = len(found_doc_types) / len(expected_docs)
    result["score"] = result["score"] * completeness_ratio

    return result


def determine_document_type(text: str) -> str:
    """Определение типа документа по содержимому"""

    text_lower = text.lower()

    # Карта ключевых слов для каждого типа документа
    doc_patterns = {
        "charter": ["устав", "учредители", "уставный капитал", "органы управления"],
        "financial_report": ["баланс", "прибыль", "убыток", "актив", "пассив", "отчет"],
        "bank_statement": ["банк", "счет", "остаток", "сальдо", "справка"],
        "license": ["лицензия", "разрешение", "право осуществления"],
        "contract": ["договор", "соглашение", "контракт", "стороны"],
        "business_plan": ["бизнес-план", "маркетинг", "финансовая модель"]
    }

    max_matches = 0
    best_type = "unknown"

    for doc_type, keywords in doc_patterns.items():
        matches = sum(1 for keyword in keywords if keyword in text_lower)
        if matches > max_matches:
            max_matches = matches
            best_type = doc_type

    return best_type if max_matches >= 2 else "unknown"


def analyze_document_content(text: str, doc_type: str) -> Dict[str, Any]:
    """Анализ содержимого документа по типу"""

    result = {
        "score": 0.7,
        "issues": [],
        "positive_findings": []
    }

    if doc_type == "charter":
        result = analyze_charter_content(text)
    elif doc_type == "financial_report":
        result = analyze_financial_report_content(text)
    elif doc_type == "bank_statement":
        result = analyze_bank_statement_content(text)
    elif doc_type == "license":
        result = analyze_license_content(text)

    return result


def analyze_charter_content(text: str) -> Dict[str, Any]:
    """Анализ содержимого устава"""

    result = {
        "score": 0.7,
        "issues": [],
        "positive_findings": []
    }

    text_lower = text.lower()

    # Обязательные разделы устава
    required_sections = {
        "наименование": ["наименование", "название", "полное наименование"],
        "адрес": ["адрес", "место нахождения", "юридический адрес"],
        "цели": ["цели", "предмет деятельности", "виды деятельности"],
        "капитал": ["уставный капитал", "размер капитала", "капитал"]
    }

    found_sections = 0
    for section, keywords in required_sections.items():
        if any(keyword in text_lower for keyword in keywords):
            found_sections += 1
            result["positive_findings"].append(f"Найден раздел: {section}")

    completeness = found_sections / len(required_sections)
    if completeness >= 0.8:
        result["score"] = 0.9
    elif completeness >= 0.6:
        result["score"] = 0.7
    else:
        result["score"] = 0.4
        result["issues"].append("Устав неполный - отсутствуют обязательные разделы")

    return result


def analyze_financial_report_content(text: str) -> Dict[str, Any]:
    """Анализ финансового отчета"""

    result = {
        "score": 0.7,
        "issues": [],
        "positive_findings": []
    }

    text_lower = text.lower()

    # Ключевые показатели
    financial_indicators = [
        "выручка", "доходы", "расходы", "прибыль", "убыток",
        "активы", "пассивы", "дебиторская", "кредиторская"
    ]

    found_indicators = sum(1 for indicator in financial_indicators
                           if indicator in text_lower)

    if found_indicators >= 6:
        result["positive_findings"].append("Отчет содержит все основные показатели")
        result["score"] = 0.9
    elif found_indicators >= 4:
        result["positive_findings"].append("Отчет содержит основные показатели")
        result["score"] = 0.7
    else:
        result["issues"].append("Неполный финансовый отчет")
        result["score"] = 0.4

    return result


def analyze_bank_statement_content(text: str) -> Dict[str, Any]:
    """Анализ банковской справки"""

    result = {
        "score": 0.8,
        "issues": [],
        "positive_findings": []
    }

    text_lower = text.lower()

    # Обязательные элементы справки
    required_elements = ["банк", "счет", "остаток", "дата"]
    found_elements = sum(1 for element in required_elements
                         if element in text_lower)

    if found_elements >= 3:
        result["positive_findings"].append("Справка содержит все необходимые данные")
        result["score"] = 0.9
    else:
        result["issues"].append("Неполная банковская справка")
        result["score"] = 0.5

    return result


def analyze_license_content(text: str) -> Dict[str, Any]:
    """Анализ лицензии"""

    result = {
        "score": 0.8,
        "issues": [],
        "positive_findings": []
    }

    text_lower = text.lower()

    # Проверяем валидность лицензии
    validity_indicators = ["действительна", "срок действия", "выдана"]
    found_validity = sum(1 for indicator in validity_indicators
                         if indicator in text_lower)

    if found_validity >= 2:
        result["positive_findings"].append("Лицензия содержит информацию о сроке действия")
        result["score"] = 0.9
    else:
        result["issues"].append("Неясен статус действия лицензии")
        result["score"] = 0.6

    return result


async def perform_llm_legal_analysis(
        form_data: Dict[str, Any],
        company_check: Dict[str, Any],
        documents_check: Dict[str, Any]
) -> Dict[str, Any]:
    """LLM анализ юридических аспектов"""

    system_prompt = """Ты - эксперт по корпоративному праву и кредитному анализу.
    Проанализируй юридические аспекты кредитной заявки компании.

    Обрати внимание на:
    1. Соответствие документов законодательству
    2. Полноту юридической информации
    3. Потенциальные правовые риски
    4. Рекомендации по снижению рисков

    Дай оценку от 0 до 1 и укажи основные проблемы, если они есть.
    Ответь в формате JSON с полями: score, risks, recommendations, confidence"""

    # Подготавливаем данные для анализа
    analysis_data = {
        "company_info": {
            "name": form_data.get("company_name", ""),
            "legal_form": form_data.get("legal_form", ""),
            "tax_number": form_data.get("tax_number", "")
        },
        "company_check_results": company_check,
        "documents_check_results": documents_check
    }

    user_message = f"""
    Проанализируй юридические аспекты заявки:

    Данные компании:
    {analysis_data['company_info']}

    Результаты проверки компании:
    {company_check}

    Результаты проверки документов:
    {documents_check}

    Дай детальную правовую оценку и рекомендации.
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
                    "score": 0.6,
                    "risks": ["Не удалось получить структурированный ответ"],
                    "recommendations": [],
                    "confidence": 0.5
                }
        else:
            # Парсим неструктурированный ответ
            score = 0.6
            if "высокий риск" in response_text.lower():
                score = 0.3
            elif "низкий риск" in response_text.lower():
                score = 0.8

            llm_result = {
                "score": score,
                "risks": [],
                "recommendations": [],
                "confidence": 0.6,
                "raw_analysis": response_text
            }

        return {
            "status": "success",
            "score": llm_result.get("score", 0.6),
            "confidence": llm_result.get("confidence", 0.6),
            "risks": llm_result.get("risks", []),
            "recommendations": llm_result.get("recommendations", []),
            "llm_analysis": response_text
        }

    except Exception as e:
        logger.error("LLM legal analysis failed", error=str(e))
        return {
            "status": "error",
            "score": 0.5,
            "confidence": 0.0,
            "risks": [f"Ошибка LLM анализа: {str(e)}"],
            "recommendations": [],
            "error": str(e)
        }


async def check_fund_requirements_compliance(form_data: Dict[str, Any]) -> Dict[str, Any]:
    """Проверка соответствия требованиям фонда"""

    result = {
        "score": 0.7,
        "compliance_checks": [],
        "violations": [],
        "recommendations": []
    }

    # Минимальные требования фонда (примерные)
    requirements = {
        "min_project_amount": 1_000_000,  # 1 млн
        "max_project_amount": 10_000_000_000,  # 10 млрд
        "max_duration_months": 84,  # 7 лет
        "allowed_activities": [
            "производство", "переработка", "инновации", "экспорт",
            "импортозамещение", "модернизация", "развитие"
        ]
    }

    # Проверка суммы проекта
    requested_amount = form_data.get("requested_amount", 0)
    if requested_amount < requirements["min_project_amount"]:
        result["violations"].append(
            f"Сумма проекта ниже минимальной ({requirements['min_project_amount']:,})"
        )
        result["score"] -= 0.3
    elif requested_amount > requirements["max_project_amount"]:
        result["violations"].append(
            f"Сумма проекта превышает максимальную ({requirements['max_project_amount']:,})"
        )
        result["score"] -= 0.4
    else:
        result["compliance_checks"].append("Сумма проекта в допустимых пределах")

    # Проверка срока проекта
    duration = form_data.get("project_duration_months", 0)
    if duration > requirements["max_duration_months"]:
        result["violations"].append(
            f"Срок проекта превышает максимальный ({requirements['max_duration_months']} мес.)"
        )
        result["score"] -= 0.2
    else:
        result["compliance_checks"].append("Срок проекта в допустимых пределах")

    # Проверка соответствия видам деятельности
    project_description = form_data.get("project_description", "").lower()
    matching_activities = [
        activity for activity in requirements["allowed_activities"]
        if activity in project_description
    ]

    if matching_activities:
        result["compliance_checks"].append(
            f"Проект соответствует приоритетным направлениям: {', '.join(matching_activities)}"
        )
        result["score"] += 0.1
    else:
        result["recommendations"].append(
            "Рекомендуется уточнить соответствие проекта приоритетным направлениям фонда"
        )

    return result


def combine_legal_results(
        company_check: Dict[str, Any],
        documents_check: Dict[str, Any],
        llm_analysis: Dict[str, Any],
        compliance_check: Dict[str, Any]
) -> Dict[str, Any]:
    """Объединение всех результатов юридической проверки"""

    # Веса компонентов
    weights = {
        "company": 0.3,
        "documents": 0.3,
        "llm": 0.25,
        "compliance": 0.15
    }

    # Расчет общей оценки
    scores = [
        company_check.get("score", 0.0) * weights["company"],
        documents_check.get("score", 0.0) * weights["documents"],
        llm_analysis.get("score", 0.0) * weights["llm"],
        compliance_check.get("score", 0.0) * weights["compliance"]
    ]

    overall_score = sum(scores)

    # Собираем все риски
    all_risks = []
    all_risks.extend(company_check.get("issues", []))
    all_risks.extend(documents_check.get("compliance_issues", []))
    all_risks.extend(llm_analysis.get("risks", []))
    all_risks.extend(compliance_check.get("violations", []))

    # Собираем рекомендации
    all_recommendations = []
    all_recommendations.extend(llm_analysis.get("recommendations", []))
    all_recommendations.extend(compliance_check.get("recommendations", []))

    # Определяем статус
    if overall_score >= 0.7 and len(all_risks) <= 2:
        status = "approved"
    elif overall_score >= 0.5 and len(all_risks) <= 5:
        status = "conditional"
    else:
        status = "rejected"

    return {
        "status": status,
        "score": overall_score,
        "confidence": llm_analysis.get("confidence", 0.7),
        "summary": f"Юридическая проверка завершена. Оценка: {overall_score:.2f}",
        "details": {
            "company_check": company_check,
            "documents_check": documents_check,
            "llm_analysis": llm_analysis,
            "compliance_check": compliance_check
        },
        "recommendations": all_recommendations,
        "risks": all_risks[:10]  # Ограничиваем до 10 рисков
    }


def create_legal_reasoning(legal_analysis: Dict[str, Any]) -> str:
    """Создание текста рассуждений юридического агента"""

    score = legal_analysis.get("score", 0.0)
    status = legal_analysis.get("status", "unknown")
    risks = legal_analysis.get("risks", [])
    recommendations = legal_analysis.get("recommendations", [])

    reasoning_parts = []

    # Общая оценка
    if score >= 0.8:
        reasoning_parts.append(f"✅ Юридическая проверка пройдена успешно с оценкой {score:.2f}")
    elif score >= 0.6:
        reasoning_parts.append(f"⚠️ Юридическая проверка пройдена условно с оценкой {score:.2f}")
    else:
        reasoning_parts.append(f"❌ Юридическая проверка не пройдена, оценка {score:.2f}")

    # Статус
    status_messages = {
        "approved": "✅ Статус: Одобрено",
        "conditional": "⚠️ Статус: Условное одобрение",
        "rejected": "❌ Статус: Отклонено"
    }
    reasoning_parts.append(status_messages.get(status, f"Статус: {status}"))

    # Детали проверки
    details = legal_analysis.get("details", {})
    company_score = details.get("company_check", {}).get("score", 0)
    documents_score = details.get("documents_check", {}).get("score", 0)
    compliance_score = details.get("compliance_check", {}).get("score", 0)

    reasoning_parts.append(f"🏢 Проверка компании: {company_score:.2f}")
    reasoning_parts.append(f"📄 Проверка документов: {documents_score:.2f}")
    reasoning_parts.append(f"📋 Соответствие требованиям: {compliance_score:.2f}")

    # Риски
    if risks:
        reasoning_parts.append(f"⚠️ Выявленные риски ({len(risks)}):")
        reasoning_parts.extend([f"  • {risk}" for risk in risks[:5]])
        if len(risks) > 5:
            reasoning_parts.append(f"  • ... и еще {len(risks) - 5} рисков")

    # Рекомендации
    if recommendations:
        reasoning_parts.append(f"💡 Рекомендации ({len(recommendations)}):")
        reasoning_parts.extend([f"  • {rec}" for rec in recommendations[:3]])

    # Итоговое заключение
    if status == "approved":
        reasoning_parts.append("✅ Заключение: Юридических препятствий для кредитования не выявлено")
    elif status == "conditional":
        reasoning_parts.append("⚠️ Заключение: Возможно кредитование при устранении выявленных замечаний")
    else:
        reasoning_parts.append("❌ Заключение: Выявлены серьезные юридические риски")

    return "\n".join(reasoning_parts)