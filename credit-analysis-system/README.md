# Credit Analysis System

Мультиагентная система для рассмотрения кредитных заявок с использованием LangGraph.

## Быстрый старт

1. Клонируйте репозиторий
2. Настройте `.env` файл с вашими API ключами
3. Запустите систему: `docker-compose up -d`

## Сервисы

- Backend API: http://localhost:8000
- Frontend: http://localhost:3000
- PostgreSQL: localhost:5432
- Redis: localhost:6379

## Архитектура

Система построена на LangGraph для управления потоком агентов:
- Валидатор
- Юридический анализ
- Риск-менеджмент
- Анализ актуальности
- Финансовый анализ
- Принятие решения

## Разработка

```bash
# Установка зависимостей backend
cd backend && pip install -r ../requirements.txt

# Установка зависимостей frontend
cd frontend && npm install

# Запуск тестов
pytest backend/tests/
```
