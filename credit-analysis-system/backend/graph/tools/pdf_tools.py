"""
Инструменты для работы с PDF документами
"""
import os
import PyPDF2
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io
from typing import Dict, Any, List
from langchain_core.tools import BaseTool

from ...config.logging import logger
from ...config.settings import settings


class PDFParserTool(BaseTool):
    """Инструмент для парсинга PDF документов"""

    name = "pdf_parser"
    description = "Парсит PDF документы и извлекает текст, метаданные и изображения"

    def _run(self, pdf_path: str) -> Dict[str, Any]:
        """Синхронная версия парсинга PDF"""
        return parse_pdf_document_sync(pdf_path)

    async def _arun(self, pdf_path: str) -> Dict[str, Any]:
        """Асинхронная версия парсинга PDF"""
        return await parse_pdf_document(pdf_path)


async def parse_pdf_document(pdf_path: str) -> Dict[str, Any]:
    """
    Асинхронная функция парсинга PDF документа
    """
    import asyncio
    import functools

    # Запускаем синхронную функцию в отдельном потоке
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        functools.partial(parse_pdf_document_sync, pdf_path)
    )
    return result


def parse_pdf_document_sync(pdf_path: str) -> Dict[str, Any]:
    """
    Синхронная функция парсинга PDF документа
    """
    try:
        if not os.path.exists(pdf_path):
            return {
                "success": False,
                "error": f"Файл не найден: {pdf_path}",
                "text": "",
                "pages": 0,
                "metadata": {}
            }

        # Проверяем размер файла
        file_size = os.path.getsize(pdf_path)
        if file_size > settings.max_file_size:
            return {
                "success": False,
                "error": f"Файл слишком большой: {file_size} байт",
                "text": "",
                "pages": 0,
                "metadata": {}
            }

        # Основной парсинг
        result = {
            "success": True,
            "text": "",
            "pages": 0,
            "metadata": {},
            "extraction_methods": []
        }

        # Метод 1: PyPDF2 (быстрый, для текстовых PDF)
        try:
            text_pypdf2 = extract_text_with_pypdf2(pdf_path)
            if text_pypdf2 and len(text_pypdf2.strip()) > 50:
                result["text"] = text_pypdf2
                result["extraction_methods"].append("PyPDF2")
                logger.info(f"Successfully extracted text using PyPDF2: {len(text_pypdf2)} characters")
        except Exception as e:
            logger.warning(f"PyPDF2 extraction failed: {str(e)}")

        # Метод 2: PyMuPDF (более мощный)
        if not result["text"] or len(result["text"].strip()) < 50:
            try:
                text_pymupdf, pages, metadata = extract_text_with_pymupdf(pdf_path)
                if text_pymupdf and len(text_pymupdf.strip()) > 50:
                    result["text"] = text_pymupdf
                    result["pages"] = pages
                    result["metadata"] = metadata
                    result["extraction_methods"].append("PyMuPDF")
                    logger.info(f"Successfully extracted text using PyMuPDF: {len(text_pymupdf)} characters")
            except Exception as e:
                logger.warning(f"PyMuPDF extraction failed: {str(e)}")

        # Метод 3: OCR (для сканированных документов)
        if not result["text"] or len(result["text"].strip()) < 50:
            try:
                text_ocr = extract_text_with_ocr(pdf_path)
                if text_ocr and len(text_ocr.strip()) > 50:
                    result["text"] = text_ocr
                    result["extraction_methods"].append("OCR")
                    logger.info(f"Successfully extracted text using OCR: {len(text_ocr)} characters")
            except Exception as e:
                logger.warning(f"OCR extraction failed: {str(e)}")

        # Проверяем итоговый результат
        if not result["text"] or len(result["text"].strip()) < 10:
            result["success"] = False
            result["error"] = "Не удалось извлечь текст из документа"

        return result

    except Exception as e:
        logger.error(f"PDF parsing failed: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "text": "",
            "pages": 0,
            "metadata": {}
        }


def extract_text_with_pypdf2(pdf_path: str) -> str:
    """Извлечение текста с помощью PyPDF2"""

    text_content = []

    with open(pdf_path, 'rb') as file:
        pdf_reader = PyPDF2.PdfReader(file)

        for page_num in range(len(pdf_reader.pages)):
            page = pdf_reader.pages[page_num]
            text = page.extract_text()

            if text:
                text_content.append(text)

    return "\n".join(text_content)


def extract_text_with_pymupdf(pdf_path: str) -> tuple:
    """Извлечение текста с помощью PyMuPDF"""

    text_content = []

    # Открываем PDF документ
    doc = fitz.open(pdf_path)

    try:
        # Извлекаем метаданные
        metadata = doc.metadata

        # Проходим по всем страницам
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            text = page.get_text()

            if text:
                text_content.append(text)

        full_text = "\n".join(text_content)
        pages_count = len(doc)

        return full_text, pages_count, metadata

    finally:
        doc.close()


def extract_text_with_ocr(pdf_path: str) -> str:
    """Извлечение текста с помощью OCR (для сканированных документов)"""

    text_content = []

    # Открываем PDF документ
    doc = fitz.open(pdf_path)

    try:
        # Обрабатываем первые 5 страниц (для экономии времени)
        max_pages = min(5, len(doc))

        for page_num in range(max_pages):
            page = doc.load_page(page_num)

            # Конвертируем страницу в изображение
            mat = fitz.Matrix(2.0, 2.0)  # Увеличиваем разрешение для лучшего OCR
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")

            # Открываем изображение с помощью PIL
            image = Image.open(io.BytesIO(img_data))

            # Предварительная обработка изображения для лучшего OCR
            image = preprocess_image_for_ocr(image)

            # Применяем OCR
            try:
                text = pytesseract.image_to_string(
                    image,
                    lang='rus+eng',  # Русский и английский языки
                    config='--psm 6 --oem 3'  # Предполагаем один однородный блок текста
                )

                if text and text.strip():
                    text_content.append(text)

            except Exception as ocr_error:
                logger.warning(f"OCR failed for page {page_num}: {str(ocr_error)}")
                continue

        return "\n".join(text_content)

    finally:
        doc.close()


def preprocess_image_for_ocr(image: Image.Image) -> Image.Image:
    """Предварительная обработка изображения для улучшения OCR"""

    try:
        # Конвертируем в оттенки серого
        if image.mode != 'L':
            image = image.convert('L')

        # Увеличиваем контрастность
        from PIL import ImageEnhance
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(2.0)

        # Увеличиваем резкость
        enhancer = ImageEnhance.Sharpness(image)
        image = enhancer.enhance(1.5)

        return image

    except Exception as e:
        logger.warning(f"Image preprocessing failed: {str(e)}")
        return image


async def extract_text_from_pdf(pdf_path: str) -> str:
    """Простая функция для извлечения только текста"""

    result = await parse_pdf_document(pdf_path)
    return result.get("text", "")


def extract_specific_data_from_text(text: str, data_type: str) -> Dict[str, Any]:
    """
    Извлечение специфических данных из текста документа
    """
    import re

    result = {
        "found": False,
        "data": {},
        "confidence": 0.0
    }

    text_lower = text.lower()

    if data_type == "company_info":
        # Ищем информацию о компании
        company_patterns = [
            r'(?:ООО|ТОО|АО|ЗАО|ОАО|ИП)\s*[«"]?([^«"»\n]{1,100})[«"»]?',
            r'наименование[:\s]*([^\n]{1,100})',
            r'организация[:\s]*([^\n]{1,100})',
        ]

        for pattern in company_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                result["found"] = True
                result["data"]["company_names"] = matches[:3]  # Первые 3 совпадения
                result["confidence"] = 0.8
                break

    elif data_type == "financial_data":
        # Ищем финансовые данные
        financial_patterns = [
            r'выручка[:\s]*([0-9\s.,]+)',
            r'доход[:\s]*([0-9\s.,]+)',
            r'прибыль[:\s]*([0-9\s.,]+)',
            r'активы[:\s]*([0-9\s.,]+)',
            r'уставный капитал[:\s]*([0-9\s.,]+)',
        ]

        financial_data = {}
        for pattern in financial_patterns:
            matches = re.findall(pattern, text_lower)
            if matches:
                key = pattern.split('[')[0]  # Берем ключевое слово
                financial_data[key] = matches[0]

        if financial_data:
            result["found"] = True
            result["data"] = financial_data
            result["confidence"] = 0.7

    elif data_type == "dates":
        # Ищем даты
        date_patterns = [
            r'\d{1,2}\.\d{1,2}\.\d{4}',
            r'\d{4}-\d{1,2}-\d{1,2}',
            r'\d{1,2}\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+\d{4}'
        ]

        dates = []
        for pattern in date_patterns:
            matches = re.findall(pattern, text)
            dates.extend(matches)

        if dates:
            result["found"] = True
            result["data"]["dates"] = list(set(dates))  # Убираем дубликаты
            result["confidence"] = 0.9

    elif data_type == "project_info":
        # Ищем информацию о проекте
        project_keywords = [
            'проект', 'инвестиц', 'развитие', 'строительство',
            'производство', 'модернизация', 'расширение'
        ]

        project_sentences = []
        sentences = text.split('.')

        for sentence in sentences:
            sentence_lower = sentence.lower()
            if any(keyword in sentence_lower for keyword in project_keywords):
                if len(sentence.strip()) > 20:  # Исключаем слишком короткие предложения
                    project_sentences.append(sentence.strip())

        if project_sentences:
            result["found"] = True
            result["data"]["project_sentences"] = project_sentences[:5]  # Первые 5 предложений
            result["confidence"] = 0.6

    return result


def check_document_type(text: str) -> str:
    """
    Определение типа документа по содержимому
    """
    text_lower = text.lower()

    # Устав компании
    if any(word in text_lower for word in ['устав', 'учредител', 'уставный капитал']):
        return "charter"

    # Финансовая отчетность
    if any(word in text_lower for word in ['баланс', 'отчет о прибыл', 'финансовый результат']):
        return "financial_report"

    # Бизнес-план
    if any(word in text_lower for word in ['бизнес-план', 'маркетинг', 'конкуренц', 'стратег']):
        return "business_plan"

    # Техническое задание
    if any(word in text_lower for word in ['техническое задание', 'тз ', 'требования', 'функционал']):
        return "technical_specification"

    # Справка из банка
    if any(word in text_lower for word in ['банк', 'счет', 'остаток', 'справка']):
        return "bank_statement"

    # Договор/контракт
    if any(word in text_lower for word in ['договор', 'контракт', 'соглашение', 'стороны']):
        return "contract"

    return "unknown"


# Инструменты для LangChain
pdf_parser_tool = PDFParserTool()


class DocumentExtractorTool(BaseTool):
    """Инструмент для извлечения специфических данных из документов"""

    name = "document_extractor"
    description = "Извлекает специфические данные (компания, финансы, даты) из текста документов"

    def _run(self, text: str, data_type: str) -> Dict[str, Any]:
        return extract_specific_data_from_text(text, data_type)

    async def _arun(self, text: str, data_type: str) -> Dict[str, Any]:
        return extract_specific_data_from_text(text, data_type)


class DocumentTypeTool(BaseTool):
    """Инструмент для определения типа документа"""

    name = "document_type_checker"
    description = "Определяет тип документа (устав, финотчет, бизнес-план и т.д.) по содержимому"

    def _run(self, text: str) -> str:
        return check_document_type(text)

    async def _arun(self, text: str) -> str:
        return check_document_type(text)


# Экспортируем инструменты
document_extractor_tool = DocumentExtractorTool()
document_type_tool = DocumentTypeTool()


def extract_tables_from_pdf(pdf_path: str) -> List[Dict[str, Any]]:
    """Извлечение таблиц из PDF документа"""

    tables = []

    try:
        doc = fitz.open(pdf_path)

        for page_num in range(min(10, len(doc))):  # Обрабатываем первые 10 страниц
            page = doc.load_page(page_num)

            # Ищем прямоугольники (потенциальные ячейки таблиц)
            drawings = page.get_drawings()

            # Простой алгоритм поиска таблиц
            if drawings:
                table_data = extract_table_from_drawings(page, drawings)
                if table_data:
                    tables.append({
                        "page": page_num + 1,
                        "data": table_data,
                        "confidence": 0.7
                    })

        doc.close()

    except Exception as e:
        logger.error(f"Table extraction failed: {str(e)}")

    return tables


def extract_table_from_drawings(page, drawings) -> List[List[str]]:
    """Извлечение данных таблицы из векторной графики"""

    # Это упрощенная реализация
    # В реальной системе нужен более сложный алгоритм

    try:
        text_instances = page.get_text("dict")

        # Группируем текст по строкам
        lines = []
        for block in text_instances.get("blocks", []):
            if "lines" in block:
                for line in block["lines"]:
                    line_text = ""
                    for span in line.get("spans", []):
                        line_text += span.get("text", "")

                    if line_text.strip():
                        lines.append(line_text.strip())

        # Если нашли строки, возвращаем их как простую таблицу
        if len(lines) > 1:
            return [line.split() for line in lines[:10]]  # Первые 10 строк

    except Exception as e:
        logger.warning(f"Table extraction from drawings failed: {str(e)}")

    return []


def extract_images_from_pdf(pdf_path: str) -> List[Dict[str, Any]]:
    """Извлечение изображений из PDF документа"""

    images = []

    try:
        doc = fitz.open(pdf_path)

        for page_num in range(min(5, len(doc))):  # Первые 5 страниц
            page = doc.load_page(page_num)
            image_list = page.get_images()

            for img_index, img in enumerate(image_list):
                try:
                    # Получаем изображение
                    xref = img[0]
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    image_ext = base_image["ext"]

                    # Анализируем изображение
                    image_analysis = analyze_image_content(image_bytes)

                    images.append({
                        "page": page_num + 1,
                        "index": img_index,
                        "size": len(image_bytes),
                        "format": image_ext,
                        "analysis": image_analysis
                    })

                except Exception as img_error:
                    logger.warning(f"Image extraction failed for page {page_num}, image {img_index}: {str(img_error)}")
                    continue

        doc.close()

    except Exception as e:
        logger.error(f"Image extraction failed: {str(e)}")

    return images


def analyze_image_content(image_bytes: bytes) -> Dict[str, Any]:
    """Базовый анализ содержимого изображения"""

    try:
        image = Image.open(io.BytesIO(image_bytes))

        analysis = {
            "width": image.width,
            "height": image.height,
            "mode": image.mode,
            "has_text": False,
            "is_chart": False,
            "is_signature": False
        }

        # Простые эвристики для определения типа изображения
        aspect_ratio = image.width / image.height
        pixel_count = image.width * image.height

        # Подозрение на подпись
        if aspect_ratio > 2.0 and pixel_count < 50000:
            analysis["is_signature"] = True

        # Подозрение на график/диаграмму
        if aspect_ratio > 1.2 and pixel_count > 100000:
            analysis["is_chart"] = True

        # Пытаемся найти текст в изображении (упрощенно)
        try:
            if pixel_count < 1000000:  # Только для небольших изображений
                text = pytesseract.image_to_string(image, config='--psm 8')
                if text and len(text.strip()) > 3:
                    analysis["has_text"] = True
                    analysis["extracted_text"] = text[:100]  # Первые 100 символов
        except:
            pass

        return analysis

    except Exception as e:
        logger.warning(f"Image analysis failed: {str(e)}")
        return {"error": str(e)}


def validate_pdf_integrity(pdf_path: str) -> Dict[str, Any]:
    """Проверка целостности PDF файла"""

    result = {
        "is_valid": True,
        "errors": [],
        "warnings": [],
        "metadata": {}
    }

    try:
        # Проверяем, что файл существует
        if not os.path.exists(pdf_path):
            result["is_valid"] = False
            result["errors"].append("Файл не найден")
            return result

        # Проверяем размер файла
        file_size = os.path.getsize(pdf_path)
        if file_size == 0:
            result["is_valid"] = False
            result["errors"].append("Файл пустой")
            return result

        if file_size > 100 * 1024 * 1024:  # 100 MB
            result["warnings"].append("Очень большой файл")

        # Пытаемся открыть файл
        try:
            doc = fitz.open(pdf_path)

            # Проверяем базовые свойства
            page_count = len(doc)
            if page_count == 0:
                result["warnings"].append("PDF не содержит страниц")
            elif page_count > 100:
                result["warnings"].append("Очень много страниц")

            # Проверяем метаданные
            metadata = doc.metadata
            result["metadata"] = {
                "pages": page_count,
                "title": metadata.get("title", ""),
                "author": metadata.get("author", ""),
                "creator": metadata.get("creator", ""),
                "file_size": file_size
            }

            # Проверяем, можем ли извлечь текст хотя бы с одной страницы
            text_found = False
            for page_num in range(min(3, page_count)):
                page = doc.load_page(page_num)
                text = page.get_text()
                if text and len(text.strip()) > 10:
                    text_found = True
                    break

            if not text_found:
                result["warnings"].append("Не удалось извлечь текст (возможно, сканированный документ)")

            doc.close()

        except Exception as open_error:
            result["is_valid"] = False
            result["errors"].append(f"Не удалось открыть PDF: {str(open_error)}")

    except Exception as e:
        result["is_valid"] = False
        result["errors"].append(f"Ошибка проверки файла: {str(e)}")

    return result


class PDFValidatorTool(BaseTool):
    """Инструмент для валидации PDF файлов"""

    name = "pdf_validator"
    description = "Проверяет целостность и валидность PDF документов"

    def _run(self, pdf_path: str) -> Dict[str, Any]:
        return validate_pdf_integrity(pdf_path)

    async def _arun(self, pdf_path: str) -> Dict[str, Any]:
        return validate_pdf_integrity(pdf_path)


class PDFTableExtractorTool(BaseTool):
    """Инструмент для извлечения таблиц из PDF"""

    name = "pdf_table_extractor"
    description = "Извлекает таблицы из PDF документов"

    def _run(self, pdf_path: str) -> List[Dict[str, Any]]:
        return extract_tables_from_pdf(pdf_path)

    async def _arun(self, pdf_path: str) -> List[Dict[str, Any]]:
        return extract_tables_from_pdf(pdf_path)


class PDFImageExtractorTool(BaseTool):
    """Инструмент для извлечения изображений из PDF"""

    name = "pdf_image_extractor"
    description = "Извлекает и анализирует изображения из PDF документов"

    def _run(self, pdf_path: str) -> List[Dict[str, Any]]:
        return extract_images_from_pdf(pdf_path)

    async def _arun(self, pdf_path: str) -> List[Dict[str, Any]]:
        return extract_images_from_pdf(pdf_path)


def extract_key_fields_from_document(text: str, document_type: str) -> Dict[str, Any]:
    """
    Интеллектуальное извлечение ключевых полей из документа
    """
    import re
    from datetime import datetime

    result = {
        "extracted_fields": {},
        "confidence": 0.0,
        "errors": []
    }

    text_lower = text.lower()

    try:
        if document_type == "financial_report":
            # Извлекаем финансовые показатели
            fields = extract_financial_fields(text)
            result["extracted_fields"] = fields
            result["confidence"] = 0.8 if fields else 0.2

        elif document_type == "charter":
            # Извлекаем данные из устава
            fields = extract_charter_fields(text)
            result["extracted_fields"] = fields
            result["confidence"] = 0.7 if fields else 0.2

        elif document_type == "business_plan":
            # Извлекаем данные из бизнес-плана
            fields = extract_business_plan_fields(text)
            result["extracted_fields"] = fields
            result["confidence"] = 0.6 if fields else 0.2

        elif document_type == "bank_statement":
            # Извлекаем банковские данные
            fields = extract_bank_statement_fields(text)
            result["extracted_fields"] = fields
            result["confidence"] = 0.9 if fields else 0.2

        else:
            # Общие поля для любого документа
            fields = extract_general_fields(text)
            result["extracted_fields"] = fields
            result["confidence"] = 0.5 if fields else 0.1

    except Exception as e:
        result["errors"].append(f"Ошибка извлечения полей: {str(e)}")
        result["confidence"] = 0.0

    return result


def extract_financial_fields(text: str) -> Dict[str, Any]:
    """Извлечение финансовых показателей"""

    fields = {}

    # Паттерны для поиска финансовых данных
    patterns = {
        "revenue": [
            r"выручка[:\s]*([0-9\s.,]+)",
            r"доходы[:\s]*([0-9\s.,]+)",
            r"оборот[:\s]*([0-9\s.,]+)"
        ],
        "profit": [
            r"прибыль[:\s]*([0-9\s.,]+)",
            r"чистая прибыль[:\s]*([0-9\s.,]+)",
            r"прибыль до налогообложения[:\s]*([0-9\s.,]+)"
        ],
        "assets": [
            r"активы[:\s]*([0-9\s.,]+)",
            r"валюта баланса[:\s]*([0-9\s.,]+)",
            r"имущество[:\s]*([0-9\s.,]+)"
        ],
        "liabilities": [
            r"обязательства[:\s]*([0-9\s.,]+)",
            r"долги[:\s]*([0-9\s.,]+)",
            r"кредиторская задолженность[:\s]*([0-9\s.,]+)"
        ]
    }

    for field_name, field_patterns in patterns.items():
        for pattern in field_patterns:
            matches = re.findall(pattern, text.lower(), re.MULTILINE)
            if matches:
                # Берем первое найденное значение
                raw_value = matches[0]
                # Пытаемся преобразовать в число
                try:
                    clean_value = re.sub(r'[^\d.,]', '', raw_value).replace(',', '.')
                    numeric_value = float(clean_value)
                    fields[field_name] = {
                        "value": numeric_value,
                        "raw_text": raw_value,
                        "confidence": 0.8
                    }
                    break
                except ValueError:
                    continue

    return fields


def extract_charter_fields(text: str) -> Dict[str, Any]:
    """Извлечение данных из устава компании"""

    fields = {}

    # Паттерны для устава
    patterns = {
        "company_name": [
            r'(?:общество с ограниченной ответственностью|ооо)\s*[«"]?([^«"»\n]{1,100})[«"»]?',
            r'полное наименование[:\s]*([^\n]{1,100})',
            r'наименование общества[:\s]*([^\n]{1,100})'
        ],
        "authorized_capital": [
            r'уставный капитал[:\s]*([0-9\s.,]+)',
            r'размер уставного капитала[:\s]*([0-9\s.,]+)'
        ],
        "address": [
            r'юридический адрес[:\s]*([^\n]{10,200})',
            r'место нахождения[:\s]*([^\n]{10,200})',
            r'адрес[:\s]*([^\n]{10,200})'
        ],
        "activity": [
            r'виды деятельности[:\s]*([^\n]{10,300})',
            r'предмет деятельности[:\s]*([^\n]{10,300})',
            r'цели деятельности[:\s]*([^\n]{10,300})'
        ]
    }

    for field_name, field_patterns in patterns.items():
        for pattern in field_patterns:
            matches = re.findall(pattern, text.lower(), re.MULTILINE | re.IGNORECASE)
            if matches:
                fields[field_name] = {
                    "value": matches[0].strip(),
                    "confidence": 0.7
                }
                break

    return fields


def extract_business_plan_fields(text: str) -> Dict[str, Any]:
    """Извлечение данных из бизнес-плана"""

    fields = {}

    # Ищем ключевые разделы бизнес-плана
    sections = {
        "project_description": [
            r'описание проекта[:\s]*([^\n]{20,500})',
            r'суть проекта[:\s]*([^\n]{20,500})',
            r'краткое описание[:\s]*([^\n]{20,500})'
        ],
        "market_analysis": [
            r'анализ рынка[:\s]*([^\n]{20,500})',
            r'рыночная ситуация[:\s]*([^\n]{20,500})',
            r'целевой рынок[:\s]*([^\n]{20,500})'
        ],
        "investment_required": [
            r'требуемые инвестиции[:\s]*([0-9\s.,]+)',
            r'объем финансирования[:\s]*([0-9\s.,]+)',
            r'сумма проекта[:\s]*([0-9\s.,]+)'
        ],
        "payback_period": [
            r'срок окупаемости[:\s]*([0-9\s.,]+)',
            r'период возврата[:\s]*([0-9\s.,]+)'
        ]
    }

    for field_name, field_patterns in sections.items():
        for pattern in field_patterns:
            matches = re.findall(pattern, text.lower(), re.MULTILINE)
            if matches:
                value = matches[0].strip()

                # Для числовых полей пытаемся извлечь число
                if field_name in ["investment_required", "payback_period"]:
                    try:
                        clean_value = re.sub(r'[^\d.,]', '', value).replace(',', '.')
                        numeric_value = float(clean_value)
                        fields[field_name] = {
                            "value": numeric_value,
                            "raw_text": value,
                            "confidence": 0.7
                        }
                    except ValueError:
                        fields[field_name] = {
                            "value": value,
                            "confidence": 0.5
                        }
                else:
                    fields[field_name] = {
                        "value": value,
                        "confidence": 0.6
                    }
                break

    return fields


def extract_bank_statement_fields(text: str) -> Dict[str, Any]:
    """Извлечение данных из банковской справки"""

    fields = {}

    patterns = {
        "account_number": [
            r'расчетный счет[:\s]*([0-9\s]{15,25})',
            r'номер счета[:\s]*([0-9\s]{15,25})',
            r'р/с[:\s]*([0-9\s]{15,25})'
        ],
        "bank_name": [
            r'банк[:\s]*([^\n]{5,100})',
            r'наименование банка[:\s]*([^\n]{5,100})'
        ],
        "balance": [
            r'остаток на счете[:\s]*([0-9\s.,]+)',
            r'остаток[:\s]*([0-9\s.,]+)',
            r'сальдо[:\s]*([0-9\s.,]+)'
        ],
        "currency": [
            r'валюта[:\s]*([а-яa-z]{3,10})',
            r'(тенге|рубл|доллар|евро)'
        ]
    }

    for field_name, field_patterns in patterns.items():
        for pattern in field_patterns:
            matches = re.findall(pattern, text.lower(), re.MULTILINE)
            if matches:
                value = matches[0].strip()

                if field_name == "balance":
                    try:
                        clean_value = re.sub(r'[^\d.,]', '', value).replace(',', '.')
                        numeric_value = float(clean_value)
                        fields[field_name] = {
                            "value": numeric_value,
                            "raw_text": value,
                            "confidence": 0.9
                        }
                    except ValueError:
                        continue
                else:
                    fields[field_name] = {
                        "value": value,
                        "confidence": 0.8
                    }
                break

    return fields


def extract_general_fields(text: str) -> Dict[str, Any]:
    """Извлечение общих полей из любого документа"""

    fields = {}

    # Общие паттерны
    patterns = {
        "dates": r'\d{1,2}[./]\d{1,2}[./]\d{4}',
        "amounts": r'[0-9\s.,]{6,}',
        "phones": r'[+]?[78][\s-]?\d{3}[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}',
        "emails": r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    }

    for field_name, pattern in patterns.items():
        matches = re.findall(pattern, text)
        if matches:
            # Ограничиваем количество найденных значений
            unique_matches = list(set(matches))[:5]
            fields[field_name] = {
                "values": unique_matches,
                "count": len(unique_matches),
                "confidence": 0.6
            }

    return fields


class PDFFieldExtractorTool(BaseTool):
    """Инструмент для извлечения ключевых полей из документов"""

    name = "pdf_field_extractor"
    description = "Извлекает ключевые поля из PDF документов в зависимости от их типа"

    def _run(self, text: str, document_type: str) -> Dict[str, Any]:
        return extract_key_fields_from_document(text, document_type)

    async def _arun(self, text: str, document_type: str) -> Dict[str, Any]:
        return extract_key_fields_from_document(text, document_type)


# Создаем экземпляр нового инструмента
pdf_field_extractor_tool = PDFFieldExtractorTool()

# Обновляем список всех PDF инструментов
PDF_TOOLS = [
    pdf_parser_tool,
    document_extractor_tool,
    document_type_tool,
    pdf_validator_tool,
    pdf_table_extractor_tool,
    pdf_image_extractor_tool,
    pdf_field_extractor_tool
]