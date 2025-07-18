"""
Инструменты для валидации данных заявок
"""
import re
from typing import Dict, Any, List, Union
from datetime import datetime, date
from langchain_core.tools import BaseTool

from ...config.logging import logger


class FormFieldValidatorTool(BaseTool):
    """Инструмент для валидации полей формы"""

    name = "form_field_validator"
    description = "Валидирует конкретное поле формы по заданным правилам"

    def _run(self, field_name: str, field_value: Any, validation_rules: Dict[str, Any]) -> Dict[str, Any]:
        return validate_form_field(field_name, field_value, validation_rules)

    async def _arun(self, field_name: str, field_value: Any, validation_rules: Dict[str, Any]) -> Dict[str, Any]:
        return validate_form_field(field_name, field_value, validation_rules)


class DocumentCompletenessTool(BaseTool):
    """Инструмент для проверки комплектности документов"""

    name = "document_completeness_checker"
    description = "Проверяет комплектность загруженных документов"

    def _run(self, documents: List[str], required_docs: List[str]) -> Dict[str, Any]:
        return check_document_completeness(documents, required_docs)

    async def _arun(self, documents: List[str], required_docs: List[str]) -> Dict[str, Any]:
        return check_document_completeness(documents, required_docs)


def validate_form_field(field_name: str, field_value: Any, validation_rules: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Валидация отдельного поля формы
    """
    if validation_rules is None:
        validation_rules = get_default_validation_rules(field_name)

    result = {
        "field_name": field_name,
        "is_valid": True,
        "errors": [],
        "warnings": [],
        "normalized_value": field_value
    }

    # Проверка на обязательность
    if validation_rules.get("required", False):
        if field_value is None or (isinstance(field_value, str) and not field_value.strip()):
            result["is_valid"] = False
            result["errors"].append(f"Поле '{field_name}' обязательно для заполнения")
            return result

    # Если поле пустое и не обязательное, считаем валидным
    if field_value is None or (isinstance(field_value, str) and not field_value.strip()):
        return result

    # Валидация по типу поля
    field_type = validation_rules.get("type", "string")

    if field_type == "email":
        result = validate_email(field_value, result)
    elif field_type == "phone":
        result = validate_phone(field_value, result)
    elif field_type == "number":
        result = validate_number(field_value, validation_rules, result)
    elif field_type == "string":
        result = validate_string(field_value, validation_rules, result)
    elif field_type == "date":
        result = validate_date(field_value, result)
    elif field_type == "inn":
        result = validate_inn(field_value, result)
    elif field_type == "amount":
        result = validate_amount(field_value, validation_rules, result)

    return result


def validate_email(email: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """Валидация email адреса"""

    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

    if not re.match(email_pattern, email):
        result["is_valid"] = False
        result["errors"].append("Некорректный формат email адреса")
    else:
        # Нормализуем email (приводим к нижнему регистру)
        result["normalized_value"] = email.lower().strip()

    return result


def validate_phone(phone: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """Валидация номера телефона"""

    # Убираем все символы кроме цифр и '+'
    clean_phone = re.sub(r'[^\d+]', '', phone)

    # Проверяем различные форматы
    patterns = [
        r'^\+7\d{10}$',  # +7XXXXXXXXXX
        r'^8\d{10}$',  # 8XXXXXXXXXX
        r'^7\d{10}$',  # 7XXXXXXXXXX
        r'^\+77\d{9}$',  # +77XXXXXXXXX (Казахстан)
        r'^\+375\d{9}$',  # +375XXXXXXXXX (Беларусь)
        r'^\+380\d{9}$',  # +380XXXXXXXXX (Украина)
    ]

    is_valid = any(re.match(pattern, clean_phone) for pattern in patterns)

    if not is_valid:
        result["is_valid"] = False
        result["errors"].append("Некорректный формат номера телефона")
    else:
        # Нормализуем номер
        if clean_phone.startswith('8') and len(clean_phone) == 11:
            result["normalized_value"] = '+7' + clean_phone[1:]
        elif clean_phone.startswith('7') and len(clean_phone) == 11:
            result["normalized_value"] = '+' + clean_phone
        else:
            result["normalized_value"] = clean_phone

    return result


def validate_number(value: Any, rules: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    """Валидация числового значения"""

    try:
        if isinstance(value, str):
            # Убираем пробелы и заменяем запятые на точки
            clean_value = value.replace(' ', '').replace(',', '.')
            number_value = float(clean_value)
        else:
            number_value = float(value)

        result["normalized_value"] = number_value

        # Проверяем диапазон
        min_value = rules.get("min")
        max_value = rules.get("max")

        if min_value is not None and number_value < min_value:
            result["is_valid"] = False
            result["errors"].append(f"Значение должно быть не менее {min_value}")

        if max_value is not None and number_value > max_value:
            result["is_valid"] = False
            result["errors"].append(f"Значение должно быть не более {max_value}")

        # Предупреждения для больших значений
        if rules.get("warn_if_large") and number_value > rules["warn_if_large"]:
            result["warnings"].append(f"Необычно большое значение: {number_value}")

    except (ValueError, TypeError):
        result["is_valid"] = False
        result["errors"].append("Некорректный числовой формат")

    return result


def validate_string(value: str, rules: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    """Валидация строкового значения"""

    # Нормализуем строку
    normalized = value.strip()
    result["normalized_value"] = normalized

    # Проверяем длину
    min_length = rules.get("min_length")
    max_length = rules.get("max_length")

    if min_length is not None and len(normalized) < min_length:
        result["is_valid"] = False
        result["errors"].append(f"Минимальная длина: {min_length} символов")

    if max_length is not None and len(normalized) > max_length:
        result["is_valid"] = False
        result["errors"].append(f"Максимальная длина: {max_length} символов")

    # Проверяем паттерн
    pattern = rules.get("pattern")
    if pattern and not re.match(pattern, normalized):
        result["is_valid"] = False
        result["errors"].append(f"Не соответствует требуемому формату")

    # Проверяем запрещенные символы
    forbidden_chars = rules.get("forbidden_chars", [])
    for char in forbidden_chars:
        if char in normalized:
            result["warnings"].append(f"Содержит нежелательный символ: {char}")

    return result


def validate_date(value: Union[str, date, datetime], result: Dict[str, Any]) -> Dict[str, Any]:
    """Валидация даты"""

    try:
        if isinstance(value, str):
            # Пробуем различные форматы даты
            date_formats = ['%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y', '%Y-%m-%d %H:%M:%S']

            parsed_date = None
            for date_format in date_formats:
                try:
                    parsed_date = datetime.strptime(value, date_format).date()
                    break
                except ValueError:
                    continue

            if parsed_date is None:
                result["is_valid"] = False
                result["errors"].append("Некорректный формат даты")
                return result

        elif isinstance(value, datetime):
            parsed_date = value.date()
        elif isinstance(value, date):
            parsed_date = value
        else:
            result["is_valid"] = False
            result["errors"].append("Неподдерживаемый тип даты")
            return result

        result["normalized_value"] = parsed_date.isoformat()

        # Проверяем разумность даты
        today = date.today()
        if parsed_date > today:
            result["warnings"].append("Дата в будущем")

        # Проверяем, не слишком ли старая дата
        years_ago = today.year - parsed_date.year
        if years_ago > 50:
            result["warnings"].append(f"Очень старая дата ({years_ago} лет назад)")

    except Exception as e:
        result["is_valid"] = False
        result["errors"].append(f"Ошибка обработки даты: {str(e)}")

    return result


def validate_inn(inn: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """Валидация ИНН с проверкой контрольных сумм"""

    # Убираем пробелы и другие символы
    clean_inn = re.sub(r'[^\d]', '', inn)

    # Проверяем длину (для ИП - 12 цифр, для юрлиц - 10 или 9)
    if len(clean_inn) not in [9, 10, 12]:
        result["is_valid"] = False
        result["errors"].append("ИНН должен содержать 9, 10 или 12 цифр")
        return result

    result["normalized_value"] = clean_inn

    # Базовая проверка на все нули или одинаковые цифры
    if len(set(clean_inn)) == 1:
        result["warnings"].append("Подозрительный ИНН (все цифры одинаковые)")
        return result

    # Проверка контрольных сумм для российских ИНН
    if len(clean_inn) == 10:
        # ИНН юридического лица
        if not validate_inn_10(clean_inn):
            result["is_valid"] = False
            result["errors"].append("Некорректная контрольная сумма ИНН")
    elif len(clean_inn) == 12:
        # ИНН физического лица
        if not validate_inn_12(clean_inn):
            result["is_valid"] = False
            result["errors"].append("Некорректная контрольная сумма ИНН")

    return result


def validate_inn_10(inn: str) -> bool:
    """Проверка контрольной суммы 10-значного ИНН"""
    coefficients = [2, 4, 10, 3, 5, 9, 4, 6, 8]

    try:
        checksum = sum(int(inn[i]) * coefficients[i] for i in range(9)) % 11
        if checksum < 10:
            return checksum == int(inn[9])
        else:
            return (checksum % 10) == int(inn[9])
    except (ValueError, IndexError):
        return False


def validate_inn_12(inn: str) -> bool:
    """Проверка контрольной суммы 12-значного ИНН"""
    coefficients1 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
    coefficients2 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]

    try:
        # Проверка первой контрольной суммы
        checksum1 = sum(int(inn[i]) * coefficients1[i] for i in range(10)) % 11
        if checksum1 < 10:
            control1 = checksum1
        else:
            control1 = checksum1 % 10

        if control1 != int(inn[10]):
            return False

        # Проверка второй контрольной суммы
        checksum2 = sum(int(inn[i]) * coefficients2[i] for i in range(11)) % 11
        if checksum2 < 10:
            control2 = checksum2
        else:
            control2 = checksum2 % 10

        return control2 == int(inn[11])

    except (ValueError, IndexError):
        return False


def validate_bin_kz(bin_kz: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """Валидация БИН для Казахстана"""

    # Убираем пробелы и другие символы
    clean_bin = re.sub(r'[^\d]', '', bin_kz)

    # БИН должен содержать 12 цифр
    if len(clean_bin) != 12:
        result["is_valid"] = False
        result["errors"].append("БИН должен содержать 12 цифр")
        return result

    result["normalized_value"] = clean_bin

    # Проверяем первые две цифры (код года)
    year_code = clean_bin[:2]
    if not (year_code >= "00" and year_code <= "99"):
        result["warnings"].append("Некорректный код года в БИН")

    # Проверяем седьмую цифру (статус)
    status_digit = clean_bin[6]
    valid_statuses = ["1", "2", "3", "4", "5", "6"]
    if status_digit not in valid_statuses:
        result["warnings"].append("Некорректный статус в БИН")

    # Проверка контрольной суммы БИН
    if not validate_bin_kz_checksum(clean_bin):
        result["is_valid"] = False
        result["errors"].append("Некорректная контрольная сумма БИН")

    return result


def validate_bin_kz_checksum(bin_kz: str) -> bool:
    """Проверка контрольной суммы БИН Казахстана"""
    coefficients = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]

    try:
        checksum = sum(int(bin_kz[i]) * coefficients[i] for i in range(11)) % 11

        if checksum < 10:
            return checksum == int(bin_kz[11])
        else:
            # Если остаток 10, пересчитываем с другими коэффициентами
            coefficients2 = [3, 4, 5, 6, 7, 8, 9, 10, 11, 1, 2]
            checksum2 = sum(int(bin_kz[i]) * coefficients2[i] for i in range(11)) % 11
            return (checksum2 if checksum2 < 10 else 0) == int(bin_kz[11])

    except (ValueError, IndexError):
        return False


def validate_address(address: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """Валидация адреса"""

    # Нормализуем адрес
    normalized = address.strip()
    result["normalized_value"] = normalized

    # Проверяем минимальную длину
    if len(normalized) < 10:
        result["is_valid"] = False
        result["errors"].append("Адрес слишком короткий")
        return result

    # Ключевые слова для адреса
    address_keywords = [
        "г.", "город", "ул.", "улица", "пр.", "проспект",
        "д.", "дом", "кв.", "квартира", "оф.", "офис",
        "область", "район", "микрорайон", "мкр"
    ]

    # Проверяем наличие ключевых слов
    found_keywords = sum(1 for keyword in address_keywords
                         if keyword.lower() in normalized.lower())

    if found_keywords == 0:
        result["warnings"].append("Адрес не содержит типичных обозначений")

    # Проверяем наличие цифр (номер дома)
    if not re.search(r'\d', normalized):
        result["warnings"].append("Адрес не содержит номеров")

    # Проверяем на подозрительные символы
    suspicious_chars = ['<', '>', '"', "'", '`']
    for char in suspicious_chars:
        if char in normalized:
            result["warnings"].append(f"Адрес содержит подозрительный символ: {char}")

    return result


def validate_currency_code(currency: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """Валидация кода валюты"""

    normalized = currency.strip().upper()
    result["normalized_value"] = normalized

    # Список допустимых валют
    valid_currencies = {
        "KZT": "Казахстанский тенге",
        "RUB": "Российский рубль",
        "USD": "Доллар США",
        "EUR": "Евро",
        "CNY": "Китайский юань",
        "KGS": "Киргизский сом",
        "UZS": "Узбекский сум",
        "BYN": "Белорусский рубль"
    }

    if normalized not in valid_currencies:
        result["warnings"].append(f"Неизвестный код валюты: {normalized}")
    else:
        result["metadata"] = {"currency_name": valid_currencies[normalized]}

    return result


class BINValidatorTool(BaseTool):
    """Инструмент для валидации БИН (Казахстан)"""

    name = "bin_validator_kz"
    description = "Валидирует БИН (Бизнес-идентификационный номер) для Казахстана"

    def _run(self, bin_value: str) -> Dict[str, Any]:
        result = {"is_valid": True, "errors": [], "warnings": []}
        return validate_bin_kz(bin_value, result)

    async def _arun(self, bin_value: str) -> Dict[str, Any]:
        result = {"is_valid": True, "errors": [], "warnings": []}
        return validate_bin_kz(bin_value, result)


class AddressValidatorTool(BaseTool):
    """Инструмент для валидации адресов"""

    name = "address_validator"
    description = "Валидирует почтовые адреса на корректность формата"

    def _run(self, address: str) -> Dict[str, Any]:
        result = {"is_valid": True, "errors": [], "warnings": []}
        return validate_address(address, result)

    async def _arun(self, address: str) -> Dict[str, Any]:
        result = {"is_valid": True, "errors": [], "warnings": []}
        return validate_address(address, result)


class CurrencyValidatorTool(BaseTool):
    """Инструмент для валидации валют"""

    name = "currency_validator"
    description = "Валидирует коды валют и проверяет их допустимость"

    def _run(self, currency: str) -> Dict[str, Any]:
        result = {"is_valid": True, "errors": [], "warnings": []}
        return validate_currency_code(currency, result)

    async def _arun(self, currency: str) -> Dict[str, Any]:
        result = {"is_valid": True, "errors": [], "warnings": []}
        return validate_currency_code(currency, result)


def validate_project_feasibility(project_data: Dict[str, Any]) -> Dict[str, Any]:
    """Базовая оценка реализуемости проекта"""

    result = {
        "feasibility_score": 0.0,
        "issues": [],
        "recommendations": [],
        "analysis": {}
    }

    try:
        # Анализ соотношения суммы и срока
        amount = project_data.get("requested_amount", 0)
        duration = project_data.get("project_duration_months", 0)

        if amount > 0 and duration > 0:
            monthly_amount = amount / duration

            if monthly_amount > 50_000_000:  # Более 50 млн в месяц
                result["issues"].append("Очень высокие месячные затраты")
                result["feasibility_score"] -= 0.2
            elif monthly_amount < 100_000:  # Менее 100 тыс в месяц
                result["issues"].append("Очень низкие месячные затраты")
                result["feasibility_score"] -= 0.1

            result["analysis"]["monthly_amount"] = monthly_amount

        # Анализ описания проекта
        description = project_data.get("project_description", "")
        if description:
            desc_length = len(description)

            if desc_length < 100:
                result["issues"].append("Слишком краткое описание проекта")
                result["feasibility_score"] -= 0.2
            elif desc_length > 2000:
                result["recommendations"].append("Рекомендуется сократить описание")

            # Проверяем наличие ключевых слов
            business_keywords = [
                "производство", "услуги", "торговля", "инновации",
                "развитие", "модернизация", "расширение", "строительство"
            ]

            found_keywords = sum(1 for keyword in business_keywords
                                 if keyword.lower() in description.lower())

            if found_keywords == 0:
                result["issues"].append("Описание не содержит ключевых бизнес-терминов")
                result["feasibility_score"] -= 0.1

            result["analysis"]["description_length"] = desc_length
            result["analysis"]["business_keywords_found"] = found_keywords

        # Анализ финансовых показателей
        annual_revenue = project_data.get("annual_revenue", 0)
        if annual_revenue > 0 and amount > 0:
            revenue_ratio = amount / annual_revenue

            if revenue_ratio > 5:  # Запрашивают более 5 годовых оборотов
                result["issues"].append("Запрашиваемая сумма значительно превышает годовую выручку")
                result["feasibility_score"] -= 0.3
            elif revenue_ratio > 2:
                result["recommendations"].append("Высокое соотношение к годовой выручке")
                result["feasibility_score"] -= 0.1

            result["analysis"]["amount_to_revenue_ratio"] = revenue_ratio

        # Базовая оценка (начинаем с 0.7)
        base_score = 0.7
        result["feasibility_score"] = max(0.0, min(1.0, base_score + result["feasibility_score"]))

        # Добавляем рекомендации
        if result["feasibility_score"] > 0.8:
            result["recommendations"].append("Проект выглядит реализуемым")
        elif result["feasibility_score"] > 0.6:
            result["recommendations"].append("Проект требует дополнительного анализа")
        else:
            result["recommendations"].append("Высокие риски реализации проекта")

    except Exception as e:
        result["issues"].append(f"Ошибка анализа реализуемости: {str(e)}")
        result["feasibility_score"] = 0.5

    return result


class ProjectFeasibilityTool(BaseTool):
    """Инструмент для оценки реализуемости проекта"""

    name = "project_feasibility_analyzer"
    description = "Анализирует реализуемость проекта на основе базовых параметров"

    def _run(self, project_data: Dict[str, Any]) -> Dict[str, Any]:
        return validate_project_feasibility(project_data)

    async def _arun(self, project_data: Dict[str, Any]) -> Dict[str, Any]:
        return validate_project_feasibility(project_data)


# Создаем экземпляры новых инструментов
bin_validator_tool = BINValidatorTool()
address_validator_tool = AddressValidatorTool()
currency_validator_tool = CurrencyValidatorTool()
project_feasibility_tool = ProjectFeasibilityTool()

# Обновляем список всех инструментов валидации
VALIDATION_TOOLS = [
    form_field_validator_tool,
    document_completeness_tool,
    data_consistency_tool,
    bin_validator_tool,
    address_validator_tool,
    currency_validator_tool,
    project_feasibility_tool
]


def validate_amount(value: Any, rules: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    """Специальная валидация для денежных сумм"""

    try:
        if isinstance(value, str):
            # Убираем валютные символы, пробелы, заменяем запятые
            clean_value = re.sub(r'[₸$€₽\s]', '', value).replace(',', '.')
            amount = float(clean_value)
        else:
            amount = float(value)

        result["normalized_value"] = amount

        # Проверяем, что сумма положительная
        if amount <= 0:
            result["is_valid"] = False
            result["errors"].append("Сумма должна быть больше нуля")

        # Проверяем разумные пределы
        if amount > 10_000_000_000:  # 10 млрд
            result["warnings"].append("Очень большая сумма")

        if amount < 10_000:  # 10 тыс
            result["warnings"].append("Очень маленькая сумма")

        # Проверяем количество знаков после запятой
        if '.' in str(amount) and len(str(amount).split('.')[1]) > 2:
            result["warnings"].append("Слишком много знаков после запятой")

    except (ValueError, TypeError):
        result["is_valid"] = False
        result["errors"].append("Некорректный формат суммы")

    return result


def check_document_completeness(documents: List[str], required_docs: List[str] = None) -> Dict[str, Any]:
    """
    Проверка комплектности документов
    """
    if required_docs is None:
        required_docs = get_required_documents()

    result = {
        "is_complete": True,
        "missing_documents": [],
        "extra_documents": [],
        "warnings": [],
        "document_analysis": {}
    }

    # Анализируем загруженные документы
    doc_types_found = []
    for doc_path in documents:
        doc_name = doc_path.lower()
        doc_type = identify_document_type(doc_name)
        doc_types_found.append(doc_type)

        result["document_analysis"][doc_path] = {
            "type": doc_type,
            "size": get_file_size_if_exists(doc_path)
        }

    # Проверяем наличие обязательных документов
    for required_doc in required_docs:
        if required_doc not in doc_types_found:
            result["missing_documents"].append(required_doc)
            result["is_complete"] = False

    # Проверяем на дублирование
    doc_type_counts = {}
    for doc_type in doc_types_found:
        doc_type_counts[doc_type] = doc_type_counts.get(doc_type, 0) + 1

    for doc_type, count in doc_type_counts.items():
        if count > 1:
            result["warnings"].append(f"Найдено {count} документов типа '{doc_type}'")

    return result


def identify_document_type(filename: str) -> str:
    """Определение типа документа по названию файла"""

    filename_lower = filename.lower()

    # Словарь ключевых слов для каждого типа документа
    type_keywords = {
        "устав": ["устав", "charter"],
        "финансовая_отчетность": ["баланс", "отчет", "финанс", "balance", "financial"],
        "бизнес_план": ["бизнес", "план", "business", "plan"],
        "справка_банк": ["справка", "банк", "statement", "bank"],
        "договор": ["договор", "контракт", "соглашение", "contract", "agreement"],
        "лицензия": ["лицензия", "разрешение", "license", "permit"],
        "паспорт_проекта": ["паспорт", "проект", "passport", "project"],
        "техническое_задание": ["тз", "техническое", "задание", "technical", "specification"]
    }

    for doc_type, keywords in type_keywords.items():
        if any(keyword in filename_lower for keyword in keywords):
            return doc_type

    return "неопределен"


def get_file_size_if_exists(filepath: str) -> int:
    """Получение размера файла, если он существует"""
    import os

    try:
        if os.path.exists(filepath):
            return os.path.getsize(filepath)
    except:
        pass

    return 0


def get_default_validation_rules(field_name: str) -> Dict[str, Any]:
    """Получение правил валидации по умолчанию для поля"""

    rules_map = {
        "company_name": {
            "type": "string",
            "required": True,
            "min_length": 2,
            "max_length": 255,
            "forbidden_chars": ["<", ">", "\"", "'"]
        },
        "email": {
            "type": "email",
            "required": True
        },
        "phone": {
            "type": "phone",
            "required": True
        },
        "tax_number": {
            "type": "inn",
            "required": True
        },
        "requested_amount": {
            "type": "amount",
            "required": True,
            "min": 10000,
            "max": 10000000000,
            "warn_if_large": 1000000000
        },
        "project_duration_months": {
            "type": "number",
            "required": True,
            "min": 1,
            "max": 120
        },
        "project_description": {
            "type": "string",
            "required": True,
            "min_length": 50,
            "max_length": 5000
        },
        "annual_revenue": {
            "type": "amount",
            "required": False,
            "min": 0,
            "warn_if_large": 10000000000
        },
        "registration_address": {
            "type": "string",
            "required": True,
            "min_length": 10,
            "max_length": 500
        }
    }

    return rules_map.get(field_name, {"type": "string", "required": False})


def get_required_documents() -> List[str]:
    """Список обязательных документов для кредитной заявки"""

    return [
        "устав",
        "финансовая_отчетность",
        "справка_банк",
        "бизнес_план"
    ]


# Создаем экземпляры инструментов
form_field_validator_tool = FormFieldValidatorTool()
document_completeness_tool = DocumentCompletenessTool()


class DataConsistencyTool(BaseTool):
    """Инструмент для проверки согласованности данных"""

    name = "data_consistency_checker"
    description = "Проверяет согласованность данных между формой и документами"

    def _run(self, form_data: Dict[str, Any], extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        return check_data_consistency(form_data, extracted_data)

    async def _arun(self, form_data: Dict[str, Any], extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        return check_data_consistency(form_data, extracted_data)


def check_data_consistency(form_data: Dict[str, Any], extracted_data: Dict[str, Any]) -> Dict[str, Any]:
    """Проверка согласованности данных между формой и документами"""

    result = {
        "is_consistent": True,
        "inconsistencies": [],
        "matches": [],
        "warnings": []
    }

    # Проверяем соответствие названия компании
    form_company = form_data.get("company_name", "").lower().strip()

    for doc_path, doc_data in extracted_data.items():
        doc_text = doc_data.get("text", "").lower()

        if form_company and form_company in doc_text:
            result["matches"].append(f"Название компании найдено в {doc_path}")
        elif form_company:
            result["warnings"].append(f"Название компании не найдено в {doc_path}")

    # Проверяем соответствие финансовых данных (если есть)
    form_revenue = form_data.get("annual_revenue")
    if form_revenue:
        # Ищем похожие суммы в документах
        revenue_found = False
        for doc_path, doc_data in extracted_data.items():
            doc_text = doc_data.get("text", "")
            # Простая проверка наличия схожих чисел
            if str(int(form_revenue)) in doc_text.replace(" ", ""):
                revenue_found = True
                result["matches"].append(f"Выручка подтверждена в {doc_path}")
                break

        if not revenue_found:
            result["warnings"].append("Выручка из формы не подтверждена документами")

    return result


# Экспортируем все инструменты
data_consistency_tool = DataConsistencyTool()

VALIDATION_TOOLS = [
    form_field_validator_tool,
    document_completeness_tool,
    data_consistency_tool
]