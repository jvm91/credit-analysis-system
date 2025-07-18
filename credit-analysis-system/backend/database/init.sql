 -- Инициализация базы данных для системы анализа кредитных заявок

-- Создание основной схемы
CREATE SCHEMA IF NOT EXISTS credit_analysis;

-- Таблица приложений
CREATE TABLE IF NOT EXISTS credit_analysis.applications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id VARCHAR(255) UNIQUE NOT NULL,
    form_data JSONB NOT NULL,
    pdf_files TEXT[] DEFAULT '{}',
    status VARCHAR(50) NOT NULL DEFAULT 'started',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processing_start_time TIMESTAMP WITH TIME ZONE,
    processing_end_time TIMESTAMP WITH TIME ZONE,
    total_processing_time FLOAT
);

-- Таблица результатов валидации
CREATE TABLE IF NOT EXISTS credit_analysis.validation_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id VARCHAR(255) REFERENCES credit_analysis.applications(application_id),
    status VARCHAR(50) NOT NULL,
    score FLOAT NOT NULL,
    errors TEXT[] DEFAULT '{}',
    warnings TEXT[] DEFAULT '{}',
    extracted_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Таблица результатов анализа
CREATE TABLE IF NOT EXISTS credit_analysis.analysis_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id VARCHAR(255) REFERENCES credit_analysis.applications(application_id),
    agent_type VARCHAR(50) NOT NULL, -- legal, risk, relevance, financial
    status VARCHAR(50) NOT NULL,
    score FLOAT NOT NULL,
    confidence FLOAT NOT NULL,
    summary TEXT,
    details JSONB,
    recommendations TEXT[] DEFAULT '{}',
    risks TEXT[] DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Таблица рассуждений агентов
CREATE TABLE IF NOT EXISTS credit_analysis.agent_reasoning (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id VARCHAR(255) REFERENCES credit_analysis.applications(application_id),
    agent VARCHAR(100) NOT NULL,
    reasoning TEXT NOT NULL,
    confidence FLOAT,
    metadata JSONB,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Таблица финальных решений
CREATE TABLE IF NOT EXISTS credit_analysis.final_decisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id VARCHAR(255) UNIQUE REFERENCES credit_analysis.applications(application_id),
    status VARCHAR(50) NOT NULL, -- approved, rejected, requires_review
    confidence FLOAT NOT NULL,
    amount_approved DECIMAL(15,2),
    conditions TEXT[] DEFAULT '{}',
    reasoning TEXT NOT NULL,
    risk_level VARCHAR(50) NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

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

-- Индексы для производительности
CREATE INDEX IF NOT EXISTS idx_applications_application_id ON credit_analysis.applications(application_id);
CREATE INDEX IF NOT EXISTS idx_applications_status ON credit_analysis.applications(status);
CREATE INDEX IF NOT EXISTS idx_applications_created_at ON credit_analysis.applications(created_at);

CREATE INDEX IF NOT EXISTS idx_validation_results_application_id ON credit_analysis.validation_results(application_id);
CREATE INDEX IF NOT EXISTS idx_analysis_results_application_id ON credit_analysis.analysis_results(application_id);
CREATE INDEX IF NOT EXISTS idx_analysis_results_agent_type ON credit_analysis.analysis_results(agent_type);

CREATE INDEX IF NOT EXISTS idx_agent_reasoning_application_id ON credit_analysis.agent_reasoning(application_id);
CREATE INDEX IF NOT EXISTS idx_agent_reasoning_agent ON credit_analysis.agent_reasoning(agent);

CREATE INDEX IF NOT EXISTS idx_final_decisions_application_id ON credit_analysis.final_decisions(application_id);
CREATE INDEX IF NOT EXISTS idx_final_decisions_status ON credit_analysis.final_decisions(status);

CREATE INDEX IF NOT EXISTS idx_checkpoints_thread_id ON credit_analysis.checkpoints(thread_id);
CREATE INDEX IF NOT EXISTS idx_checkpoints_created_at ON credit_analysis.checkpoints(created_at);

-- Функция для автоматического обновления updated_at
CREATE OR REPLACE FUNCTION credit_analysis.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Триггер для автоматического обновления updated_at
CREATE TRIGGER update_applications_updated_at
    BEFORE UPDATE ON credit_analysis.applications
    FOR EACH ROW EXECUTE FUNCTION credit_analysis.update_updated_at_column();