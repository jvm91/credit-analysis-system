-- Полная инициализация базы данных для Credit Analysis System
-- Файл: backend/database/init.sql

-- Создание расширений
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "btree_gin";

-- Создание основной схемы
CREATE SCHEMA IF NOT EXISTS credit_analysis;

-- Установка search_path
SET search_path TO credit_analysis, public;

-- =====================================================
-- ОСНОВНЫЕ ТАБЛИЦЫ
-- =====================================================

-- Таблица приложений (основная)
CREATE TABLE IF NOT EXISTS credit_analysis.applications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    application_id VARCHAR(255) UNIQUE NOT NULL,
    form_data JSONB NOT NULL,
    pdf_files TEXT[] DEFAULT '{}',
    status VARCHAR(50) NOT NULL DEFAULT 'started',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processing_start_time TIMESTAMP WITH TIME ZONE,
    processing_end_time TIMESTAMP WITH TIME ZONE,
    total_processing_time FLOAT,

    -- Дополнительные поля для аналитики
    company_name VARCHAR(500),
    project_name VARCHAR(500),
    requested_amount DECIMAL(15,2),
    project_duration_months INTEGER,

    -- Метаданные
    created_by VARCHAR(255),
    ip_address INET,
    user_agent TEXT,

    CONSTRAINT applications_status_check
        CHECK (status IN ('started', 'validating', 'validation_complete',
                         'legal_checking', 'legal_check_complete',
                         'risk_analyzing', 'risk_analysis_complete',
                         'relevance_checking', 'relevance_check_complete',
                         'financial_analyzing', 'financial_analysis_complete',
                         'decision_making', 'completed', 'error', 'rejected')),
    CONSTRAINT applications_amount_check
        CHECK (requested_amount IS NULL OR requested_amount >= 0),
    CONSTRAINT applications_duration_check
        CHECK (project_duration_months IS NULL OR
               (project_duration_months >= 1 AND project_duration_months <= 120))
);

-- Таблица результатов валидации
CREATE TABLE IF NOT EXISTS credit_analysis.validation_results (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    application_id VARCHAR(255) NOT NULL,
    status VARCHAR(50) NOT NULL,
    score FLOAT NOT NULL CHECK (score >= 0 AND score <= 1),
    errors TEXT[] DEFAULT '{}',
    warnings TEXT[] DEFAULT '{}',
    extracted_data JSONB,
    component_scores JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    FOREIGN KEY (application_id) REFERENCES credit_analysis.applications(application_id)
        ON DELETE CASCADE ON UPDATE CASCADE,

    CONSTRAINT validation_status_check
        CHECK (status IN ('success', 'warning', 'error'))
);

-- Таблица результатов анализа агентов
CREATE TABLE IF NOT EXISTS credit_analysis.analysis_results (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    application_id VARCHAR(255) NOT NULL,
    agent_type VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL,
    score FLOAT NOT NULL CHECK (score >= 0 AND score <= 1),
    confidence FLOAT NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    summary TEXT,
    details JSONB,
    recommendations TEXT[] DEFAULT '{}',
    risks TEXT[] DEFAULT '{}',
    processing_time FLOAT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    FOREIGN KEY (application_id) REFERENCES credit_analysis.applications(application_id)
        ON DELETE CASCADE ON UPDATE CASCADE,

    CONSTRAINT analysis_agent_type_check
        CHECK (agent_type IN ('legal', 'risk', 'relevance', 'financial')),
    CONSTRAINT analysis_status_check
        CHECK (status IN ('approved', 'conditional', 'rejected', 'error'))
);

-- Таблица рассуждений агентов
CREATE TABLE IF NOT EXISTS credit_analysis.agent_reasoning (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    application_id VARCHAR(255) NOT NULL,
    agent VARCHAR(100) NOT NULL,
    reasoning TEXT NOT NULL,
    confidence FLOAT CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    metadata JSONB,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    FOREIGN KEY (application_id) REFERENCES credit_analysis.applications(application_id)
        ON DELETE CASCADE ON UPDATE CASCADE,

    CONSTRAINT agent_reasoning_agent_check
        CHECK (agent IN ('validator', 'legal_checker', 'risk_manager',
                        'relevance_checker', 'financial_analyzer', 'decision_maker'))
);

-- Таблица финальных решений
CREATE TABLE IF NOT EXISTS credit_analysis.final_decisions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    application_id VARCHAR(255) UNIQUE NOT NULL,
    status VARCHAR(50) NOT NULL,
    confidence FLOAT NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    amount_approved DECIMAL(15,2) CHECK (amount_approved IS NULL OR amount_approved >= 0),
    conditions TEXT[] DEFAULT '{}',
    reasoning TEXT NOT NULL,
    risk_level VARCHAR(50) NOT NULL,
    overall_score FLOAT CHECK (overall_score >= 0 AND overall_score <= 1),
    component_breakdown JSONB,
    expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    FOREIGN KEY (application_id) REFERENCES credit_analysis.applications(application_id)
        ON DELETE CASCADE ON UPDATE CASCADE,

    CONSTRAINT decisions_status_check
        CHECK (status IN ('approved', 'conditional_approval', 'requires_review', 'rejected')),
    CONSTRAINT decisions_risk_check
        CHECK (risk_level IN ('low', 'moderate', 'high', 'critical'))
);

-- =====================================================
-- LANGGRAPH CHECKPOINTING ТАБЛИЦЫ
-- =====================================================

-- Таблица для LangGraph checkpointing
CREATE TABLE IF NOT EXISTS credit_analysis.checkpoints (
    thread_id VARCHAR(255) NOT NULL,
    checkpoint_id VARCHAR(255) NOT NULL,
    parent_checkpoint_id VARCHAR(255),
    checkpoint_data JSONB NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    PRIMARY KEY (thread_id, checkpoint_id)
);

-- Таблица для checkpoint writes
CREATE TABLE IF NOT EXISTS credit_analysis.checkpoint_writes (
    thread_id VARCHAR(255) NOT NULL,
    checkpoint_id VARCHAR(255) NOT NULL,
    task_id VARCHAR(255) NOT NULL,
    idx INTEGER NOT NULL,
    channel VARCHAR(255) NOT NULL,
    value JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    FOREIGN KEY (thread_id, checkpoint_id)
        REFERENCES credit_analysis.checkpoints(thread_id, checkpoint_id)
        ON DELETE CASCADE,

    PRIMARY KEY (thread_id, checkpoint_id, task_id, idx)
);

-- =====================================================
-- АНАЛИТИЧЕСКИЕ ТАБЛИЦЫ
-- =====================================================

-- Таблица статистики
CREATE TABLE IF NOT EXISTS credit_analysis.application_statistics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    date DATE NOT NULL DEFAULT CURRENT_DATE,
    total_applications INTEGER DEFAULT 0,
    approved_applications INTEGER DEFAULT 0,
    rejected_applications INTEGER DEFAULT 0,
    conditional_applications INTEGER DEFAULT 0,
    avg_processing_time FLOAT,
    avg_requested_amount DECIMAL(15,2),
    avg_approved_amount DECIMAL(15,2),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE(date)
);

-- Таблица для аудита
CREATE TABLE IF NOT EXISTS credit_analysis.audit_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    application_id VARCHAR(255),
    action VARCHAR(100) NOT NULL,
    details JSONB,
    user_id VARCHAR(255),
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    FOREIGN KEY (application_id) REFERENCES credit_analysis.applications(application_id)
        ON DELETE SET NULL ON UPDATE CASCADE
);

-- =====================================================
-- ИНДЕКСЫ ДЛЯ ПРОИЗВОДИТЕЛЬНОСТИ
-- =====================================================

-- Основные индексы для applications
CREATE INDEX IF NOT EXISTS idx_applications_application_id
    ON credit_analysis.applications(application_id);
CREATE INDEX IF NOT EXISTS idx_applications_status
    ON credit_analysis.applications(status);
CREATE INDEX IF NOT EXISTS idx_applications_created_at
    ON credit_analysis.applications(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_applications_company_name
    ON credit_analysis.applications USING gin(company_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_applications_requested_amount
    ON credit_analysis.applications(requested_amount DESC);
CREATE INDEX IF NOT EXISTS idx_applications_form_data
    ON credit_analysis.applications USING gin(form_data);

-- Индексы для validation_results
CREATE INDEX IF NOT EXISTS idx_validation_results_application_id
    ON credit_analysis.validation_results(application_id);
CREATE INDEX IF NOT EXISTS idx_validation_results_score
    ON credit_analysis.validation_results(score DESC);
CREATE INDEX IF NOT EXISTS idx_validation_results_created_at
    ON credit_analysis.validation_results(created_at DESC);

-- Индексы для analysis_results
CREATE INDEX IF NOT EXISTS idx_analysis_results_application_id
    ON credit_analysis.analysis_results(application_id);
CREATE INDEX IF NOT EXISTS idx_analysis_results_agent_type
    ON credit_analysis.analysis_results(agent_type);
CREATE INDEX IF NOT EXISTS idx_analysis_results_score
    ON credit_analysis.analysis_results(agent_type, score DESC);
CREATE INDEX IF NOT EXISTS idx_analysis_results_created_at
    ON credit_analysis.analysis_results(created_at DESC);

-- Индексы для agent_reasoning
CREATE INDEX IF NOT EXISTS idx_agent_reasoning_application_id
    ON credit_analysis.agent_reasoning(application_id);
CREATE INDEX IF NOT EXISTS idx_agent_reasoning_agent
    ON credit_analysis.agent_reasoning(agent);
CREATE INDEX IF NOT EXISTS idx_agent_reasoning_timestamp
    ON credit_analysis.agent_reasoning(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_agent_reasoning_text_search
    ON credit_analysis.agent_reasoning USING gin(reasoning gin_trgm_ops);

-- Индексы для final_decisions
CREATE INDEX IF NOT EXISTS idx_final_decisions_application_id
    ON credit_analysis.final_decisions(application_id);
CREATE INDEX IF NOT EXISTS idx_final_decisions_status
    ON credit_analysis.final_decisions(status);
CREATE INDEX IF NOT EXISTS idx_final_decisions_risk_level
    ON credit_analysis.final_decisions(risk_level);
CREATE INDEX IF NOT EXISTS idx_final_decisions_amount_approved
    ON credit_analysis.final_decisions(amount_approved DESC);
CREATE INDEX IF NOT EXISTS idx_final_decisions_created_at
    ON credit_analysis.final_decisions(created_at DESC);

-- Индексы для checkpoints (LangGraph)
CREATE INDEX IF NOT EXISTS idx_checkpoints_thread_id
    ON credit_analysis.checkpoints(thread_id);
CREATE INDEX IF NOT EXISTS idx_checkpoints_created_at
    ON credit_analysis.checkpoints(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_checkpoint_writes_thread_checkpoint
    ON credit_analysis.checkpoint_writes(thread_id, checkpoint_id);

-- Индексы для аналитики
CREATE INDEX IF NOT EXISTS idx_application_statistics_date
    ON credit_analysis.application_statistics(date DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_application_id
    ON credit_analysis.audit_log(application_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_action
    ON credit_analysis.audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_log_created_at
    ON credit_analysis.audit_log(created_at DESC);

-- =====================================================
-- ФУНКЦИИ И ТРИГГЕРЫ
-- =====================================================

-- Функция для автоматического обновления updated_at
CREATE OR REPLACE FUNCTION credit_analysis.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Триггер для автоматического обновления updated_at
DROP TRIGGER IF EXISTS update_applications_updated_at ON credit_analysis.applications;
CREATE TRIGGER update_applications_updated_at
    BEFORE UPDATE ON credit_analysis.applications
    FOR EACH ROW EXECUTE FUNCTION credit_analysis.update_updated_at_column();

-- Функция для извлечения данных из form_data в денормализованные поля
CREATE OR REPLACE FUNCTION credit_analysis.extract_form_data_fields()
RETURNS TRIGGER AS $$
BEGIN
    NEW.company_name = NEW.form_data->>'company_name';
    NEW.project_name = NEW.form_data->>'project_name';

    -- Безопасное преобразование в числа
    BEGIN
        NEW.requested_amount = (NEW.form_data->>'requested_amount')::DECIMAL(15,2);
    EXCEPTION WHEN OTHERS THEN
        NEW.requested_amount = NULL;
    END;

    BEGIN
        NEW.project_duration_months = (NEW.form_data->>'project_duration_months')::INTEGER;
    EXCEPTION WHEN OTHERS THEN
        NEW.project_duration_months = NULL;
    END;

    RETURN NEW;
END;
$$ language 'plpgsql';

-- Триггер для извлечения данных
DROP TRIGGER IF EXISTS extract_form_data ON credit_analysis.applications;
CREATE TRIGGER extract_form_data
    BEFORE INSERT OR UPDATE ON credit_analysis.applications
    FOR EACH ROW EXECUTE FUNCTION credit_analysis.extract_form_data_fields();

-- Функция для обновления статистики
CREATE OR REPLACE FUNCTION credit_analysis.update_daily_statistics()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO credit_analysis.application_statistics (
        date,
        total_applications,
        approved_applications,
        rejected_applications,
        conditional_applications,
        avg_processing_time,
        avg_requested_amount,
        avg_approved_amount
    )
    SELECT
        CURRENT_DATE,
        COUNT(*) as total,
        COUNT(*) FILTER (WHERE fd.status = 'approved') as approved,
        COUNT(*) FILTER (WHERE fd.status = 'rejected') as rejected,
        COUNT(*) FILTER (WHERE fd.status IN ('conditional_approval', 'requires_review')) as conditional,
        AVG(a.total_processing_time) as avg_time,
        AVG(a.requested_amount) as avg_requested,
        AVG(fd.amount_approved) as avg_approved
    FROM credit_analysis.applications a
    LEFT JOIN credit_analysis.final_decisions fd ON a.application_id = fd.application_id
    WHERE a.created_at::date = CURRENT_DATE
    ON CONFLICT (date) DO UPDATE SET
        total_applications = EXCLUDED.total_applications,
        approved_applications = EXCLUDED.approved_applications,
        rejected_applications = EXCLUDED.rejected_applications,
        conditional_applications = EXCLUDED.conditional_applications,
        avg_processing_time = EXCLUDED.avg_processing_time,
        avg_requested_amount = EXCLUDED.avg_requested_amount,
        avg_approved_amount = EXCLUDED.avg_approved_amount;

    RETURN NULL;
END;
$$ language 'plpgsql';

-- Триггер для обновления статистики
DROP TRIGGER IF EXISTS update_statistics ON credit_analysis.final_decisions;
CREATE TRIGGER update_statistics
    AFTER INSERT OR UPDATE OR DELETE ON credit_analysis.final_decisions
    FOR EACH STATEMENT EXECUTE FUNCTION credit_analysis.update_daily_statistics();

-- =====================================================
-- ПРЕДСТАВЛЕНИЯ ДЛЯ АНАЛИТИКИ
-- =====================================================

-- Представление для полной информации о заявках
CREATE OR REPLACE VIEW credit_analysis.applications_full AS
SELECT
    a.*,
    vr.score as validation_score,
    vr.status as validation_status,

    -- Агрегированные оценки по агентам
    ar_legal.score as legal_score,
    ar_legal.status as legal_status,
    ar_risk.score as risk_score,
    ar_risk.status as risk_status,
    ar_relevance.score as relevance_score,
    ar_relevance.status as relevance_status,
    ar_financial.score as financial_score,
    ar_financial.status as financial_status,

    -- Финальное решение
    fd.status as final_status,
    fd.confidence as final_confidence,
    fd.amount_approved,
    fd.risk_level,
    fd.overall_score,
    fd.expires_at,

    -- Статистика по времени
    EXTRACT(EPOCH FROM (a.processing_end_time - a.processing_start_time))/60 as processing_minutes,

    -- Количество рассуждений
    (SELECT COUNT(*) FROM credit_analysis.agent_reasoning ar
     WHERE ar.application_id = a.application_id) as reasoning_count

FROM credit_analysis.applications a
LEFT JOIN credit_analysis.validation_results vr ON a.application_id = vr.application_id
LEFT JOIN credit_analysis.analysis_results ar_legal ON a.application_id = ar_legal.application_id AND ar_legal.agent_type = 'legal'
LEFT JOIN credit_analysis.analysis_results ar_risk ON a.application_id = ar_risk.application_id AND ar_risk.agent_type = 'risk'
LEFT JOIN credit_analysis.analysis_results ar_relevance ON a.application_id = ar_relevance.application_id AND ar_relevance.agent_type = 'relevance'
LEFT JOIN credit_analysis.analysis_results ar_financial ON a.application_id = ar_financial.application_id AND ar_financial.agent_type = 'financial'
LEFT JOIN credit_analysis.final_decisions fd ON a.application_id = fd.application_id;

-- Представление для дашборда
CREATE OR REPLACE VIEW credit_analysis.dashboard_stats AS
SELECT
    -- Общие статистики
    COUNT(*) as total_applications,
    COUNT(*) FILTER (WHERE status = 'completed') as completed_applications,
    COUNT(*) FILTER (WHERE fd.status = 'approved') as approved_applications,
    COUNT(*) FILTER (WHERE fd.status = 'rejected') as rejected_applications,

    -- Средние значения
    AVG(total_processing_time) as avg_processing_time,
    AVG(requested_amount) as avg_requested_amount,
    AVG(fd.amount_approved) as avg_approved_amount,

    -- За сегодня
    COUNT(*) FILTER (WHERE created_at::date = CURRENT_DATE) as today_applications,

    -- За последние 7 дней
    COUNT(*) FILTER (WHERE created_at >= CURRENT_DATE - INTERVAL '7 days') as week_applications,

    -- Распределение по рискам
    COUNT(*) FILTER (WHERE fd.risk_level = 'low') as low_risk_count,
    COUNT(*) FILTER (WHERE fd.risk_level = 'moderate') as moderate_risk_count,
    COUNT(*) FILTER (WHERE fd.risk_level = 'high') as high_risk_count,
    COUNT(*) FILTER (WHERE fd.risk_level = 'critical') as critical_risk_count

FROM credit_analysis.applications a
LEFT JOIN credit_analysis.final_decisions fd ON a.application_id = fd.application_id;

-- =====================================================
-- ФУНКЦИИ ДЛЯ API
-- =====================================================

-- Функция для получения статуса заявки
CREATE OR REPLACE FUNCTION credit_analysis.get_application_status(app_id VARCHAR)
RETURNS TABLE (
    application_id VARCHAR,
    current_status VARCHAR,
    progress_percentage INTEGER,
    agent_count INTEGER,
    has_decision BOOLEAN,
    processing_time_minutes FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        a.application_id,
        a.status,
        CASE
            WHEN a.status = 'started' THEN 5
            WHEN a.status = 'validating' THEN 15
            WHEN a.status = 'validation_complete' THEN 20
            WHEN a.status = 'legal_checking' THEN 30
            WHEN a.status = 'legal_check_complete' THEN 40
            WHEN a.status = 'risk_analyzing' THEN 50
            WHEN a.status = 'risk_analysis_complete' THEN 60
            WHEN a.status = 'relevance_checking' THEN 70
            WHEN a.status = 'relevance_check_complete' THEN 80
            WHEN a.status = 'financial_analyzing' THEN 85
            WHEN a.status = 'financial_analysis_complete' THEN 90
            WHEN a.status = 'decision_making' THEN 95
            WHEN a.status = 'completed' THEN 100
            ELSE 0
        END as progress,
        (SELECT COUNT(*) FROM credit_analysis.agent_reasoning ar
         WHERE ar.application_id = a.application_id)::INTEGER as agents,
        (fd.id IS NOT NULL) as decision_exists,
        COALESCE(
            EXTRACT(EPOCH FROM (a.processing_end_time - a.processing_start_time))/60,
            EXTRACT(EPOCH FROM (NOW() - a.processing_start_time))/60
        ) as proc_time
    FROM credit_analysis.applications a
    LEFT JOIN credit_analysis.final_decisions fd ON a.application_id = fd.application_id
    WHERE a.application_id = app_id;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- НАЧАЛЬНЫЕ ДАННЫЕ
-- =====================================================

-- Создание пользователя для приложения (опционально)
-- CREATE USER credit_app WITH PASSWORD 'secure_password';
-- GRANT CONNECT ON DATABASE credit_analysis TO credit_app;
-- GRANT USAGE ON SCHEMA credit_analysis TO credit_app;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA credit_analysis TO credit_app;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA credit_analysis TO credit_app;

-- Создание начальной статистики
INSERT INTO credit_analysis.application_statistics (date, total_applications)
VALUES (CURRENT_DATE, 0)
ON CONFLICT (date) DO NOTHING;

-- Логирование успешной инициализации
INSERT INTO credit_analysis.audit_log (action, details)
VALUES ('database_initialized', '{"version": "1.0.0", "timestamp": "' || NOW() || '"}');

-- Установка поиска по умолчанию
ALTER DATABASE credit_analysis SET search_path TO credit_analysis, public;

COMMIT;