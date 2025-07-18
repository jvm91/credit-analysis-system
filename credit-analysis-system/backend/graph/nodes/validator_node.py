"""
Узел валидации кредитных заявок
"""
import re
from typing import Dict, Any, List
from datetime import datetime

from ..state import CreditApplicationState, ProcessingStatus, add_agent_reasoning, update_processing_step
from ..tools.pdf_tools import parse_pdf_document, extract_text_from_pdf
from ..tools.validation_tools import validate_form_field, check_document_completeness
from ...services.llm_service import llm_service
from ...config.logging import logger


async def validator_node(state: CreditApplicationState) -> CreditApplicationState:
    """
    Узел валидации заявки и документов
    """
    logger.info("Starting validation", application_id=state["application_id"])

    # Обновляем статус
    state = update_processing_step(state, ProcessingStatus.VALIDATING)

    try:
        # 1. Валидация данных формы
        form_validation_result = await validate_form_data(state["form_data"])

        # 2. Валидация PDF документов
        pdf_validation_result = await validate_pdf_documents(
            state["pdf_files"],
            state["form_data"]
        )

        # 3. LLM анализ соответствия данных
        llm_validation_result = await perform_llm_validation(
            state["form_data"],
            pdf_validation_result.get("extracted_data", {})
        )

        # 4. Объединение результатов валидации
        overall_validation = combine_validation_results(
            form_validation_result,
            pdf_validation_result,
            llm_validation_result
        )

        # 5. Добавляем рассуждения валидатора
        reasoning = create_validation_reasoning(overall_validation)
        state = add_agent_reasoning(
            state,
            "validator",
            reasoning,
            confidence=overall_validation["score"],
            metadata={
                "form_errors": len(form_validation_result["errors"]),
                "pdf_errors": len(pdf_validation_result["errors"]),
                "llm_confidence": llm_validation_result.get("confidence", 0.0)
            }
        )

        # 6. Обновляем состояние с результатами
        state["validation_result"] = overall_validation
        state["validation_errors"] = overall_validation["errors"]
        state = update_processing_step(state, ProcessingStatus.VALIDATION_COMPLETE)

        logger.info(
            "Validation completed",
            application_id=state["application_id"],
            score=overall_validation["score"],
            errors_count=len(overall_validation["errors"])
        )

        return state

    except Exception as e:
        error_msg = f"Validation failed: {str(e)}"
        logger.error("Validation error", application_id=state["application_id"], error=str(e))

        # Добавляем ошибку к состоянию
        state["errors"].append(error_msg)
        state["validation_result"] = {
            "status": "error",
            "score": 0.0,
            "errors": [error_msg],
            "warnings": [],
            "extracted_data": {}
        }

        return state


async def validate_form_data(form_data: Dict[str, Any]) -> Dict[str, Any]:
    """Валидация данных формы заявки"""

    errors = []
    warnings = []
    score_factors = []

    # Обязательные поля
    required_fields = [
        "company_name", "legal_form", "tax_number", "registration_address",
        "contact_person", "phone", "email", "project_name",
        "project_description", "requested_amount", "project_duration_months"
    ]

    # Проверка обязательных полей
    for field in required_fields:
        if not form_data.get(field):
            errors.append(f"Отсутствует обязательное поле: {field}")
        else:
            score_factors.append(1.0)

    # Валидация email
    email = form_data.get("email", "")
    if email:
        email_pattern = r'^[^@]+@[^@]+\.[^@]+$'
        if not re.match(email_pattern, email):
            errors.append("Некорректный формат email")
        else:
            score_factors.append(1.0)

    # Валидация телефона (базовая)
    phone = form_data.get("phone", "")
    if phone:
        # Удаляем все кроме цифр
        phone_digits = re.sub(r'[^\d]', '', phone)
        if len(phone_digits) < 10:
            errors.append("Некорректный формат телефона")
        else:
            score_factors.append(1.0)

    # Валидация суммы
    requested_amount = form_data.get("requested_amount", 0)
    if isinstance(requested_amount, (int, float)):
        if requested_amount <= 0:
            errors.append("Запрашиваемая сумма должна быть больше 0")
        elif requested_amount > 1000000000:  # 1 млрд
            warnings.append("Очень большая запрашиваемая сумма")
            score_factors.append(0.8)
        else:
            score_factors.append(1.0)
    else:
        errors.append("Некорректный формат запрашиваемой суммы")

    # Валидация длительности проекта
    duration = form_data.get("project_duration_months", 0)
    if isinstance(duration, int):
        if duration <= 0:
            errors.append("Длительность проекта должна быть больше 0")
        elif duration > 120:  # 10 лет
            warnings.append("Очень длительный проект (более 10 лет)")
            score_factors.append(0.9)
        else:
            score_factors.append(1.0)
    else:
        errors.append("Некорректный формат длительности проекта")

    # Валидация описания проекта
    description = form_data.get("project_description", "")
    if len(description) < 50:
        warnings.append("Слишком краткое описание проекта")
        score_factors.append(0.7)
    elif len(description) > 5000:
        warnings.append("Слишком длинное описание проекта")
        score_factors.append(0.9)
    else:
        score_factors.append(1.0)

    # Валидация финансовых данных (опциональных)
    financial_fields = ["annual_revenue", "net_profit", "total_assets", "debt_amount"]
    for field in financial_fields:
        value = form_data.get(field)
        if value is not None:
            if not isinstance(value, (int, float)) or value < 0:
                warnings.append(f"Некорректное значение в поле {field}")
                score_factors.append(0.8)
            else:
                score_factors.append(1.0)

    # Расчет общей оценки
    if not score_factors:
        score = 0.0
    else:
        score = sum(score_factors) / len(score_factors)

    # Снижаем оценку за ошибки
    if errors:
        score = max(0.0, score - len(errors) * 0.2)

    return {
        "status": "error" if errors else "success",
        "score": score,
        "errors": errors,
        "warnings": warnings,
        "validated_fields": list(form_data.keys())
    }


async def validate_pdf_documents(pdf_files: List[str], form_data: Dict[str, Any]) -> Dict[str, Any]:
    """Валидация PDF документов"""

    errors = []
    warnings = []
    extracted_data = {}
    score_factors = []

    if not pdf_files:
        warnings.append("Не загружены PDF документы")
        return {
            "status": "warning",
            "score": 0.7,
            "errors": errors,
            "warnings": warnings,
            "extracted_data": extracted_data
        }

    for pdf_file in pdf_files:
        try:
            # Парсинг PDF документа
            pdf_data = await parse_pdf_document(pdf_file)

            if pdf_data.get("success"):
                # Извлекаем текст
                text_content = pdf_data.get("text", "")
                extracted_data[pdf_file] = {
                    "text": text_content,
                    "pages": pdf_data.get("pages", 0),
                    "metadata": pdf_data.get("metadata", {})
                }

                # Проверяем качество извлеченного текста
                if len(text_content) < 100:
                    warnings.append(f"Мало текста в документе {pdf_file}")
                    score_factors.append(0.6)
                else:
                    score_factors.append(1.0)

                # Проверяем наличие ключевых слов
                company_name = form_data.get("company_name", "").lower()
                if company_name and company_name in text_content.lower():
                    score_factors.append(1.0)
                else:
                    warnings.append(f"Не найдено название компании в документе {pdf_file}")
                    score_factors.append(0.8)

            else:
                error_msg = f"Не удалось обработать документ {pdf_file}: {pdf_data.get('error', 'Неизвестная ошибка')}"
                errors.append(error_msg)
                score_factors.append(0.0)

        except Exception as e:
            error_msg = f"Ошибка при обработке {pdf_file}: {str(e)}"
            errors.append(error_msg)
            score_factors.append(0.0)

    # Расчет общей оценки
    if not score_factors:
        score = 0.0
    else:
        score = sum(score_factors) / len(score_factors)

    return {
        "status": "error" if errors else ("warning" if warnings else "success"),
        "score": score,
        "errors": errors,
        "warnings": warnings,
        "extracted_data": extracted_data
    }


async def perform_llm_validation(form_data: Dict[str, Any], extracted_data: Dict[str, Any]) -> Dict[str, Any]:
    """LLM анализ соответствия данных формы и документов"""

    # Подготавливаем данные для анализа
    form_summary = {
        "company_name": form_data.get("company_name", ""),
        "project_name": form_data.get("project_name", ""),
        "requested_amount": form_data.get("requested_amount", 0),
        "project_description": form_data.get("project_description", "")[:500]  # Ограничиваем длину
    }

    # Объединяем тексты из всех документов
    all_document_text = ""
    for file_path, data in extracted_data.items():
        text = data.get("text", "")
        all_document_text += f"\n\nДокумент {file_path}:\n{text[:1000]}"  # Ограничиваем каждый документ

    system_prompt = """Ты - эксперт по валидации кредитных заявок. 
    Твоя задача - проанализировать соответствие данных в форме заявки и в приложенных документах.

    Проверь:
    1. Соответствует ли название компании в документах данным в форме
    2. Согласуются ли финансовые данные
    3. Соответствует ли описание проекта документам
    4. Есть ли противоречия или несоответствия
    5. Достаточно ли информации для принятия решения

    Дай оценку от 0 до 1, где:
    - 0.9-1.0: Отличное соответствие, все данные согласованы
    - 0.7-0.8: Хорошее соответствие, незначительные расхождения
    - 0.5-0.6: Удовлетворительно, есть некоторые несоответствия
    - 0.3-0.4: Плохое соответствие, много противоречий
    - 0.0-0.2: Критические несоответствия

    Ответь в формате JSON с полями: score, issues, positive_aspects, confidence"""

    user_message = f"""
    Данные из формы заявки:
    {form_summary}

    Данные из документов:
    {all_document_text[:2000]}

    Проанализируй соответствие данных и дай детальную оценку.
    """

    try:
        from langchain_core.messages import SystemMessage, HumanMessage

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message)
        ]

        response = await llm_service.call(messages)
        response_text = response.content

        # Пытаемся извлечь JSON из ответа
        import json

        # Ищем JSON в тексте ответа
        json_start = response_text.find('{')
        json_end = response_text.rfind('}') + 1

        if json_start != -1 and json_end > json_start:
            json_text = response_text[json_start:json_end]
            try:
                llm_result = json.loads(json_text)
            except json.JSONDecodeError:
                # Если не удалось распарсить JSON, создаем структуру вручную
                llm_result = {
                    "score": 0.7,  # Средняя оценка по умолчанию
                    "issues": ["Не удалось получить структурированный ответ от LLM"],
                    "positive_aspects": [],
                    "confidence": 0.5
                }
        else:
            # Если JSON не найден, анализируем текст
            score = 0.7  # По умолчанию
            if "отличное" in response_text.lower() or "excellent" in response_text.lower():
                score = 0.9
            elif "хорошее" in response_text.lower() or "good" in response_text.lower():
                score = 0.8
            elif "плохое" in response_text.lower() or "poor" in response_text.lower():
                score = 0.4
            elif "критические" in response_text.lower() or "critical" in response_text.lower():
                score = 0.2

            llm_result = {
                "score": score,
                "issues": [],
                "positive_aspects": [],
                "confidence": 0.6,
                "raw_response": response_text
            }

        return {
            "status": "success",
            "score": llm_result.get("score", 0.7),
            "confidence": llm_result.get("confidence", 0.6),
            "issues": llm_result.get("issues", []),
            "positive_aspects": llm_result.get("positive_aspects", []),
            "llm_analysis": response_text
        }

    except Exception as e:
        logger.error("LLM validation failed", error=str(e))
        return {
            "status": "error",
            "score": 0.5,  # Нейтральная оценка при ошибке
            "confidence": 0.0,
            "issues": [f"Ошибка LLM анализа: {str(e)}"],
            "positive_aspects": [],
            "error": str(e)
        }


def combine_validation_results(
        form_result: Dict[str, Any],
        pdf_result: Dict[str, Any],
        llm_result: Dict[str, Any]
) -> Dict[str, Any]:
    """Объединение результатов всех типов валидации"""

    # Веса для разных типов валидации
    weights = {
        "form": 0.4,  # 40% - данные формы критически важны
        "pdf": 0.3,  # 30% - документы важны, но не всегда обязательны
        "llm": 0.3  # 30% - LLM анализ для соответствия
    }

    # Собираем оценки
    scores = [
        form_result.get("score", 0.0) * weights["form"],
        pdf_result.get("score", 0.0) * weights["pdf"],
        llm_result.get("score", 0.0) * weights["llm"]
    ]

    overall_score = sum(scores)

    # Собираем все ошибки и предупреждения
    all_errors = []
    all_errors.extend(form_result.get("errors", []))
    all_errors.extend(pdf_result.get("errors", []))
    all_errors.extend(llm_result.get("issues", []))

    all_warnings = []
    all_warnings.extend(form_result.get("warnings", []))
    all_warnings.extend(pdf_result.get("warnings", []))

    # Определяем общий статус
    if all_errors:
        status = "error" if len(all_errors) > 3 else "warning"
    elif all_warnings:
        status = "warning"
    else:
        status = "success"

    # Собираем извлеченные данные
    extracted_data = {}
    extracted_data.update(pdf_result.get("extracted_data", {}))
    if llm_result.get("positive_aspects"):
        extracted_data["llm_positive_aspects"] = llm_result["positive_aspects"]

    return {
        "status": status,
        "score": overall_score,
        "errors": all_errors,
        "warnings": all_warnings,
        "extracted_data": extracted_data,
        "component_scores": {
            "form_validation": form_result.get("score", 0.0),
            "pdf_validation": pdf_result.get("score", 0.0),
            "llm_validation": llm_result.get("score", 0.0)
        },
        "llm_confidence": llm_result.get("confidence", 0.0)
    }


def create_validation_reasoning(validation_result: Dict[str, Any]) -> str:
    """Создание текста рассуждений валидатора"""

    score = validation_result.get("score", 0.0)
    errors = validation_result.get("errors", [])
    warnings = validation_result.get("warnings", [])
    component_scores = validation_result.get("component_scores", {})

    reasoning_parts = []

    # Общая оценка
    if score >= 0.8:
        reasoning_parts.append(f"✅ Валидация успешно пройдена с высокой оценкой {score:.2f}")
    elif score >= 0.6:
        reasoning_parts.append(f"⚠️ Валидация пройдена удовлетворительно с оценкой {score:.2f}")
    else:
        reasoning_parts.append(f"❌ Валидация не пройдена, низкая оценка {score:.2f}")

    # Детали по компонентам
    form_score = component_scores.get("form_validation", 0.0)
    pdf_score = component_scores.get("pdf_validation", 0.0)
    llm_score = component_scores.get("llm_validation", 0.0)

    reasoning_parts.append(f"📋 Проверка формы: {form_score:.2f}")
    reasoning_parts.append(f"📄 Проверка документов: {pdf_score:.2f}")
    reasoning_parts.append(f"🤖 LLM анализ соответствия: {llm_score:.2f}")

    # Ошибки
    if errors:
        reasoning_parts.append(f"❌ Обнаружено ошибок: {len(errors)}")
        reasoning_parts.extend([f"  • {error}" for error in errors[:3]])
        if len(errors) > 3:
            reasoning_parts.append(f"  • ... и еще {len(errors) - 3} ошибок")

    # Предупреждения
    if warnings:
        reasoning_parts.append(f"⚠️ Предупреждения: {len(warnings)}")
        reasoning_parts.extend([f"  • {warning}" for warning in warnings[:3]])

    # Рекомендация
    if score >= 0.7 and len(errors) == 0:
        reasoning_parts.append("✅ Рекомендация: Продолжить обработку заявки")
    elif score >= 0.5 and len(errors) <= 2:
        reasoning_parts.append("⚠️ Рекомендация: Продолжить с осторожностью")
    else:
        reasoning_parts.append("❌ Рекомендация: Отклонить заявку на этапе валидации")

    return "\n".join(reasoning_parts)