.PHONY: help build up down logs clean test

help:  ## Показать справку
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

build:  ## Собрать все контейнеры
	docker-compose build

up:  ## Запустить все сервисы
	docker-compose up -d

down:  ## Остановить все сервисы
	docker-compose down

logs:  ## Показать логи
	docker-compose logs -f

clean:  ## Очистить Docker образы и контейнеры
	docker-compose down -v
	docker system prune -f

test:  ## Запустить тесты
	docker-compose exec backend pytest tests/

install:  ## Установить зависимости для разработки
	cd backend && pip install -r ../requirements.txt
	cd frontend && npm install

dev-backend:  ## Запустить backend в режиме разработки
	cd backend && uvicorn main:app --reload --host 0.0.0.0 --port 8000

dev-frontend:  ## Запустить frontend в режиме разработки
	cd frontend && npm start

setup-env:  ## Настроить переменные окружения
	@echo "Отредактируйте .env файл и укажите ваши API ключи"
	@echo "Особенно важно: OPENAI_API_KEY"
