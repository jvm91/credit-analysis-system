#!/bin/bash

# Скрипт для создания структуры проекта Credit Analysis System
# Использование: chmod +x setup_project.sh && ./setup_project.sh

set -e  # Остановка при ошибке

echo "🚀 Создание проекта Credit Analysis System..."

# Основная директория проекта
PROJECT_NAME="credit-analysis-system"

# Проверяем, существует ли уже проект
if [ -d "$PROJECT_NAME" ]; then
    echo "❌ Директория $PROJECT_NAME уже существует!"
    echo "Удалить существующую директорию? (y/N)"
    read -r response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        rm -rf "$PROJECT_NAME"
        echo "✅ Существующая директория удалена"
    else
        echo "❌ Отменено пользователем"
        exit 1
    fi
fi

# Создание структуры директорий
echo "📁 Создание структуры директорий..."

mkdir -p "$PROJECT_NAME"/{backend/{graph/{nodes,edges,tools},services,models,database/{migrations,repositories},api/{routes,middleware,validators},config},frontend/src/{components/{ApplicationForm,GraphVisualization,AgentProgress,ReasoningDisplay,DecisionSummary},pages,services,utils},tests,docker,docs}

cd "$PROJECT_NAME"

# Создание корневых файлов
echo "📄 Создание корневых файлов..."

# .env файл
cat > .env << 'EOF'
# Основные настройки
APP_NAME=Credit Analysis System
DEBUG=false
VERSION=1.0.0

# База данных
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/credit_analysis

# Redis
REDIS_URL=redis://localhost:6379

# LLM API ключи
OPENAI_API_KEY=your-openai-api-key-here
ANTHROPIC_API_KEY=your-anthropic-api-key-here
DEFAULT_LLM_PROVIDER=openai
DEFAULT_MODEL=gpt-4

# Файловая система
UPLOAD_DIR=./uploads
MAX_FILE_SIZE=52428800
ALLOWED_EXTENSIONS=.pdf,.doc,.docx

# Безопасность
SECRET_KEY=your-super-secret-key-change-in-production-123456
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# CORS
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000

# Логирование
LOG_LEVEL=INFO
LOG_FORMAT=json

# Производительность
MAX_CONCURRENT_REQUESTS=100
REQUEST_TIMEOUT=300
EOF

# requirements.txt
cat > requirements.txt << 'EOF'
# LangGraph и LangChain
langgraph==0.0.55
langchain==0.1.17
langchain-openai==0.1.8
langchain-community==0.0.37
langchain-core==0.1.52

# FastAPI и веб-сервер
fastapi==0.111.0
uvicorn[standard]==0.30.1
websockets==12.0

# База данных
sqlalchemy==2.0.30
psycopg2-binary==2.9.9
alembic==1.13.1

# Redis для кэширования
redis==5.0.4
hiredis==2.3.2

# Обработка PDF
PyPDF2==3.0.1
pymupdf==1.24.5
pytesseract==0.3.10
Pillow==10.3.0

# Общие утилиты
pydantic==2.7.1
python-multipart==0.0.9
aiofiles==23.2.1
structlog==24.1.0
python-dotenv==1.0.1

# Тестирование
pytest==8.2.1
pytest-asyncio==0.23.7
httpx==0.27.0

# Разработка
black==24.4.2
isort==5.13.2
flake8==7.0.0
mypy==1.10.0
EOF

# docker-compose.yml
cat > docker-compose.yml << 'EOF'
version: '3.8'

services:
  # PostgreSQL для основной БД и checkpointing
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: credit_analysis
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./backend/database/init.sql:/docker-entrypoint-initdb.d/init.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5

  # Redis для кэширования и сессий
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  # Backend API
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://postgres:postgres@postgres:5432/credit_analysis
      - REDIS_URL=redis://redis:6379
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - LOG_LEVEL=INFO
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./backend:/app
      - ./uploads:/app/uploads
    command: uvicorn main:app --host 0.0.0.0 --port 8000 --reload

  # Frontend
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
    environment:
      - REACT_APP_API_URL=http://localhost:8000
      - REACT_APP_WS_URL=ws://localhost:8000
    volumes:
      - ./frontend/src:/app/src
    depends_on:
      - backend

volumes:
  postgres_data:
  redis_data:
EOF

# README.md
cat > README.md << 'EOF'
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
EOF

echo "🐳 Создание backend файлов..."

# Backend Dockerfile
cat > backend/Dockerfile << 'EOF'
FROM python:3.11-slim

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    tesseract-ocr \
    tesseract-ocr-rus \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копирование и установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование кода приложения
COPY . .

# Создание директории для загрузок
RUN mkdir -p /app/uploads

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
EOF

# Создание __init__.py файлов
echo "📝 Создание __init__.py файлов..."

cat > backend/__init__.py << 'EOF'
"""
Credit Analysis System Backend
"""
EOF

cat > backend/config/__init__.py << 'EOF'
"""
Configuration
"""
EOF

cat > backend/graph/__init__.py << 'EOF'
"""
LangGraph components
"""
EOF

cat > backend/graph/nodes/__init__.py << 'EOF'
"""
Graph nodes (agents)
"""
EOF

cat > backend/graph/edges/__init__.py << 'EOF'
"""
Graph edge conditions
"""
EOF

cat > backend/graph/tools/__init__.py << 'EOF'
"""
Tools for agents
"""
EOF

cat > backend/services/__init__.py << 'EOF'
"""
Business logic services
"""
EOF

cat > backend/models/__init__.py << 'EOF'
"""
Data models
"""
EOF

cat > backend/database/__init__.py << 'EOF'
"""
Database components
"""
EOF

cat > backend/database/repositories/__init__.py << 'EOF'
"""
Database repositories
"""
EOF

cat > backend/api/__init__.py << 'EOF'
"""
API components
"""
EOF

cat > backend/api/routes/__init__.py << 'EOF'
"""
API routes
"""
EOF

cat > backend/api/middleware/__init__.py << 'EOF'
"""
API middleware
"""
EOF

cat > backend/api/validators/__init__.py << 'EOF'
"""
Request validators
"""
EOF

# Создание базовых файлов с заглушками
echo "📋 Создание базовых backend файлов..."

# settings.py
cat > backend/config/settings.py << 'EOF'
"""
Конфигурация приложения
"""
import os
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Настройки приложения"""
    
    # Основные настройки
    app_name: str = "Credit Analysis System"
    debug: bool = False
    version: str = "1.0.0"
    
    # База данных
    database_url: str = "postgresql://postgres:postgres@localhost:5432/credit_analysis"
    
    # Redis
    redis_url: str = "redis://localhost:6379"
    
    # LLM настройки
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    default_llm_provider: str = "openai"
    default_model: str = "gpt-4"
    
    # Файловая система
    upload_dir: str = "./uploads"
    max_file_size: int = 50 * 1024 * 1024  # 50MB
    allowed_extensions: list = [".pdf", ".doc", ".docx"]
    
    # Безопасность
    secret_key: str = "your-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    
    # CORS
    cors_origins: list = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    
    # Логирование
    log_level: str = "INFO"
    log_format: str = "json"
    
    # Производительность
    max_concurrent_requests: int = 100
    request_timeout: int = 300  # 5 минут
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Глобальный экземпляр настроек
settings = Settings()
EOF

# main.py (упрощенная версия)
cat > backend/main.py << 'EOF'
"""
Основное приложение FastAPI
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.settings import settings

# Создание приложения
app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description="Мультиагентная система рассмотрения кредитных заявок"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    """Корневой эндпоинт"""
    return {
        "message": "Credit Analysis System API",
        "version": settings.version,
        "status": "running"
    }

@app.get("/health")
async def health_check():
    """Проверка здоровья системы"""
    return {
        "status": "healthy",
        "services": {
            "database": "connected",
            "redis": "connected",
            "llm": "available"
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug
    )
EOF

echo "🌐 Создание frontend файлов..."

# Frontend package.json
cat > frontend/package.json << 'EOF'
{
  "name": "credit-analysis-frontend",
  "version": "1.0.0",
  "private": true,
  "dependencies": {
    "@testing-library/jest-dom": "^5.17.0",
    "@testing-library/react": "^13.4.0",
    "@testing-library/user-event": "^14.5.2",
    "@types/jest": "^27.5.2",
    "@types/node": "^16.18.68",
    "@types/react": "^18.2.42",
    "@types/react-dom": "^18.2.17",
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-scripts": "5.0.1",
    "typescript": "^4.9.5",
    "web-vitals": "^2.1.4",
    "@mui/material": "^5.15.0",
    "@mui/icons-material": "^5.15.0",
    "@emotion/react": "^11.11.1",
    "@emotion/styled": "^11.11.0",
    "reactflow": "^11.10.1",
    "axios": "^1.6.2",
    "react-router-dom": "^6.20.1",
    "zustand": "^4.4.7",
    "react-dropzone": "^14.2.3",
    "react-hook-form": "^7.48.2",
    "@hookform/resolvers": "^3.3.2",
    "yup": "^1.3.3"
  },
  "scripts": {
    "start": "react-scripts start",
    "build": "react-scripts build",
    "test": "react-scripts test",
    "eject": "react-scripts eject"
  },
  "eslintConfig": {
    "extends": [
      "react-app",
      "react-app/jest"
    ]
  },
  "browserslist": {
    "production": [
      ">0.2%",
      "not dead",
      "not op_mini all"
    ],
    "development": [
      "last 1 chrome version",
      "last 1 firefox version",
      "last 1 safari version"
    ]
  },
  "devDependencies": {
    "@types/react-router-dom": "^5.3.3"
  },
  "proxy": "http://localhost:8000"
}
EOF

# Frontend Dockerfile
cat > frontend/Dockerfile << 'EOF'
FROM node:18-alpine

WORKDIR /app

# Копирование package.json и package-lock.json
COPY package*.json ./

# Установка зависимостей
RUN npm ci --only=production

# Копирование исходного кода
COPY . .

# Сборка приложения
RUN npm run build

# Использование nginx для раздачи статики
FROM nginx:alpine

# Копирование собранного приложения
COPY --from=0 /app/build /usr/share/nginx/html

# Копирование конфигурации nginx
COPY nginx.conf /etc/nginx/nginx.conf

EXPOSE 3000

CMD ["nginx", "-g", "daemon off;"]
EOF

# nginx.conf для frontend
cat > frontend/nginx.conf << 'EOF'
events {
    worker_connections 1024;
}

http {
    include       /etc/nginx/mime.types;
    default_type  application/octet-stream;

    server {
        listen 3000;
        server_name localhost;

        root /usr/share/nginx/html;
        index index.html;

        location / {
            try_files $uri $uri/ /index.html;
        }

        location /api {
            proxy_pass http://backend:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
        }
    }
}
EOF

echo "🗄️ Создание дополнительных файлов..."

# .gitignore
cat > .gitignore << 'EOF'
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
pip-wheel-metadata/
share/python-wheels/
*.egg-info/
.installed.cfg
*.egg
MANIFEST

# Virtual environments
.env
.venv
env/
venv/
ENV/
env.bak/
venv.bak/

# IDEs
.vscode/
.idea/
*.swp
*.swo

# Node.js
node_modules/
npm-debug.log*
yarn-debug.log*
yarn-error.log*

# Frontend build
frontend/build/
frontend/dist/

# Database
*.db
*.sqlite

# Uploads
uploads/

# Logs
*.log
logs/

# Docker
.dockerignore

# OS
.DS_Store
Thumbs.db

# Secrets
.env.local
.env.production
EOF

# Makefile для удобства
cat > Makefile << 'EOF'
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
EOF

# Создание директории uploads
mkdir -p uploads

echo "✅ Проект успешно создан!"
echo ""
echo "📋 Следующие шаги:"
echo "1. cd $PROJECT_NAME"
echo "2. Отредактируйте .env файл и укажите ваши API ключи"
echo "3. docker-compose up -d"
echo "4. Откройте http://localhost:8000 для API"
echo "5. Откройте http://localhost:3000 для Frontend"
echo ""
echo "🔧 Полезные команды:"
echo "   make help     - Показать все доступные команды"
echo "   make up       - Запустить сервисы"
echo "   make logs     - Посмотреть логи"
echo "   make down     - Остановить сервисы"
echo ""
echo "🎉 Готово! Проект создан в директории: $PROJECT_NAME"