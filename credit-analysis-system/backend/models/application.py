"""
Модели данных для кредитных заявок
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID, uuid4

from sqlalchemy import Column, String, DateTime, Float, Text, ARRAY, JSON
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.sql import func
from pydantic import BaseModel, Field

from ..database.connection import Base


class ApplicationModel(Base):
    """Модель кредитной заявки в БД"""

    __tablename__ = "applications"
    __table_args__ = {"schema": "credit_analysis"}

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    application_id = Column(String(255), unique=True, nullable=False)
    form_data = Column(JSON, nullable=False)
    pdf_files = Column(ARRAY(Text), default=[])
    status = Column(String(50), nullable=False, default="started")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())
    processing_start_time = Column(DateTime(timezone=True))
    processing_end_time = Column(DateTime(timezone=True))
    total_processing_time = Column(Float)


class ValidationResultModel(Base):
    """Модель результатов валидации"""

    __tablename__ = "validation_results"
    __table_args__ = {"schema": "credit_analysis"}

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    application_id = Column(String(255), nullable=False)
    status = Column(String(50), nullable=False)
    score = Column(Float, nullable=False)
    errors = Column(ARRAY(Text), default=[])
    warnings = Column(ARRAY(Text), default=[])
    extracted_data = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AnalysisResultModel(Base):
    """Модель результатов анализа агентов"""

    __tablename__ = "analysis_results"
    __table_args__ = {"schema": "credit_analysis"}

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    application_id = Column(String(255), nullable=False)
    agent_type = Column(String(50), nullable=False)
    status = Column(String(50), nullable=False)
    score = Column(Float, nullable=False)
    confidence = Column(Float, nullable=False)
    summary = Column(Text)
    details = Column(JSON)
    recommendations = Column(ARRAY(Text), default=[])
    risks = Column(ARRAY(Text), default=[])
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AgentReasoningModel(Base):
    """Модель рассуждений агентов"""

    __tablename__ = "agent_reasoning"
    __table_args__ = {"schema": "credit_analysis"}

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    application_id = Column(String(255), nullable=False)
    agent = Column(String(100), nullable=False)
    reasoning = Column(Text, nullable=False)
    confidence = Column(Float)
    metadata = Column(JSON)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())


class FinalDecisionModel(Base):
    """Модель финального решения"""

    __tablename__ = "final_decisions"
    __table_args__ = {"schema": "credit_analysis"}

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    application_id = Column(String(255), unique=True, nullable=False)
    status = Column(String(50), nullable=False)
    confidence = Column(Float, nullable=False)
    amount_approved = Column(Float)
    conditions = Column(ARRAY(Text), default=[])
    reasoning = Column(Text, nullable=False)
    risk_level = Column(String(50), nullable=False)
    expires_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# Pydantic схемы для API

class ApplicationSubmission(BaseModel):
    """Схема для подачи заявки"""

    company_name: str = Field(..., min_length=1, max_length=255)
    legal_form: str
    tax_number: str = Field(..., min_length=1)
    registration_address: str
    contact_person: str
    phone: str
    email: str = Field(..., regex=r'^[^@]+@[^@]+\.[^@]+$')

    # Проектные данные
    project_name: str = Field(..., min_length=1, max_length=255)
    project_description: str = Field(..., min_length=10)
    requested_amount: float = Field(..., gt=0)
    project_duration_months: int = Field(..., gt=0, le=120)

    # Финансовые данные
    annual_revenue: Optional[float] = Field(None, ge=0)
    net_profit: Optional[float] = None
    total_assets: Optional[float] = Field(None, ge=0)
    debt_amount: Optional[float] = Field(None, ge=0)

    class Config:
        str_strip_whitespace = True


class ApplicationResponse(BaseModel):
    """Схема ответа при подаче заявки"""

    application_id: str
    status: str
    message: str
    created_at: datetime


class ApplicationStatus(BaseModel):
    """Схема статуса обработки заявки"""

    application_id: str
    current_step: str
    status: str
    progress_percentage: int
    estimated_completion_time: Optional[datetime]

    # Результаты агентов
    validation_complete: bool = False
    legal_check_complete: bool = False
    risk_analysis_complete: bool = False
    relevance_check_complete: bool = False
    financial_analysis_complete: bool = False

    # Краткая сводка
    summary: Optional[str] = None
    next_steps: List[str] = []


class AgentReasoningResponse(BaseModel):
    """Схема рассуждений агента"""

    agent: str
    reasoning: str
    confidence: Optional[float]
    timestamp: datetime
    metadata: Optional[Dict[str, Any]] = None


class FinalDecisionResponse(BaseModel):
    """Схема финального решения"""

    application_id: str
    status: str  # approved, rejected, requires_review
    confidence: float
    amount_approved: Optional[float]
    conditions: List[str]
    reasoning: str
    risk_level: str
    expires_at: Optional[datetime]
    created_at: datetime