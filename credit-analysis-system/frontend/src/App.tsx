import React, { useState, useEffect } from 'react';
import './App.css';

interface ApplicationForm {
  company_name: string;
  legal_form: string;
  tax_number: string;
  registration_address: string;
  contact_person: string;
  phone: string;
  email: string;
  project_name: string;
  project_description: string;
  requested_amount: number;
  project_duration_months: number;
  annual_revenue?: number;
  net_profit?: number;
  total_assets?: number;
  debt_amount?: number;
}

interface ApplicationStatus {
  application_id: string;
  current_step: string;
  status: string;
  progress_percentage: number;
  summary: string;
}

interface AgentReasoning {
  agent: string;
  reasoning: string;
  confidence?: number;
  timestamp: string;
}

interface FinalDecision {
  status: string;
  confidence: number;
  amount_approved?: number;
  conditions: string[];
  reasoning: string;
  risk_level: string;
}

function App() {
  const [currentView, setCurrentView] = useState<'form' | 'status' | 'result'>('form');
  const [applicationId, setApplicationId] = useState<string>('');
  const [status, setStatus] = useState<ApplicationStatus | null>(null);
  const [reasoning, setReasoning] = useState<AgentReasoning[]>([]);
  const [finalDecision, setFinalDecision] = useState<FinalDecision | null>(null);
  const [ws, setWs] = useState<WebSocket | null>(null);

  const [formData, setFormData] = useState<ApplicationForm>({
    company_name: '',
    legal_form: '',
    tax_number: '',
    registration_address: '',
    contact_person: '',
    phone: '',
    email: '',
    project_name: '',
    project_description: '',
    requested_amount: 0,
    project_duration_months: 12,
    annual_revenue: undefined,
    net_profit: undefined,
    total_assets: undefined,
    debt_amount: undefined
  });

  // WebSocket подключение
  useEffect(() => {
    if (applicationId && currentView === 'status') {
      const websocket = new WebSocket(`ws://localhost:8000/ws/applications/${applicationId}`);

      websocket.onopen = () => {
        console.log('WebSocket connected');
        setWs(websocket);
      };

      websocket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        console.log('WebSocket message:', data);

        if (data.type === 'initial_state' || data.type === 'agent_update') {
          // Обновляем статус
          fetchStatus();
          fetchReasoning();
        } else if (data.type === 'final_decision') {
          setFinalDecision(data.decision);
          setCurrentView('result');
        }
      };

      websocket.onclose = () => {
        console.log('WebSocket disconnected');
        setWs(null);
      };

      return () => {
        websocket.close();
      };
    }
  }, [applicationId, currentView]);

  const submitApplication = async (e: React.FormEvent) => {
    e.preventDefault();

    try {
      const response = await fetch('http://localhost:8000/applications/submit', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(formData),
      });

      if (!response.ok) {
        throw new Error('Failed to submit application');
      }

      const result = await response.json();
      setApplicationId(result.application_id);
      setCurrentView('status');

    } catch (error) {
      console.error('Error submitting application:', error);
      alert('Ошибка при подаче заявки');
    }
  };

  const fetchStatus = async () => {
    if (!applicationId) return;

    try {
      const response = await fetch(`http://localhost:8000/applications/${applicationId}/status`);
      if (response.ok) {
        const statusData = await response.json();
        setStatus(statusData);
      }
    } catch (error) {
      console.error('Error fetching status:', error);
    }
  };

  const fetchReasoning = async () => {
    if (!applicationId) return;

    try {
      const response = await fetch(`http://localhost:8000/applications/${applicationId}/reasoning`);
      if (response.ok) {
        const reasoningData = await response.json();
        setReasoning(reasoningData.reasoning);
      }
    } catch (error) {
      console.error('Error fetching reasoning:', error);
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: name.includes('amount') || name.includes('months') || name.includes('revenue') || name.includes('profit') || name.includes('assets') || name.includes('debt')
        ? Number(value) || 0
        : value
    }));
  };

  if (currentView === 'form') {
    return (
      <div className="App">
        <header className="App-header">
          <h1>🏦 Credit Analysis System</h1>
          <p>Мультиагентная система рассмотрения кредитных заявок</p>
        </header>

        <main style={{ padding: '20px', maxWidth: '800px', margin: '0 auto' }}>
          <form onSubmit={submitApplication} style={{ textAlign: 'left' }}>
            <h2>📝 Подача кредитной заявки</h2>

            <div style={{ marginBottom: '20px' }}>
              <h3>🏢 Информация о компании</h3>

              <div style={{ marginBottom: '10px' }}>
                <label>Название компании *</label>
                <input
                  type="text"
                  name="company_name"
                  value={formData.company_name}
                  onChange={handleInputChange}
                  required
                  style={{ width: '100%', padding: '8px', marginTop: '4px' }}
                />
              </div>

              <div style={{ display: 'flex', gap: '10px', marginBottom: '10px' }}>
                <div style={{ flex: 1 }}>
                  <label>Организационно-правовая форма *</label>
                  <select
                    name="legal_form"
                    value={formData.legal_form}
                    onChange={handleInputChange}
                    required
                    style={{ width: '100%', padding: '8px', marginTop: '4px' }}
                  >
                    <option value="">Выберите форму</option>
                    <option value="ТОО">ТОО</option>
                    <option value="АО">АО</option>
                    <option value="ИП">ИП</option>
                    <option value="ООО">ООО</option>
                  </select>
                </div>

                <div style={{ flex: 1 }}>
                  <label>БИН/ИНН *</label>
                  <input
                    type="text"
                    name="tax_number"
                    value={formData.tax_number}
                    onChange={handleInputChange}
                    required
                    style={{ width: '100%', padding: '8px', marginTop: '4px' }}
                  />
                </div>
              </div>

              <div style={{ marginBottom: '10px' }}>
                <label>Юридический адрес *</label>
                <input
                  type="text"
                  name="registration_address"
                  value={formData.registration_address}
                  onChange={handleInputChange}
                  required
                  style={{ width: '100%', padding: '8px', marginTop: '4px' }}
                />
              </div>

              <div style={{ display: 'flex', gap: '10px', marginBottom: '10px' }}>
                <div style={{ flex: 1 }}>
                  <label>Контактное лицо *</label>
                  <input
                    type="text"
                    name="contact_person"
                    value={formData.contact_person}
                    onChange={handleInputChange}
                    required
                    style={{ width: '100%', padding: '8px', marginTop: '4px' }}
                  />
                </div>

                <div style={{ flex: 1 }}>
                  <label>Телефон *</label>
                  <input
                    type="tel"
                    name="phone"
                    value={formData.phone}
                    onChange={handleInputChange}
                    required
                    style={{ width: '100%', padding: '8px', marginTop: '4px' }}
                  />
                </div>
              </div>

              <div style={{ marginBottom: '10px' }}>
                <label>Email *</label>
                <input
                  type="email"
                  name="email"
                  value={formData.email}
                  onChange={handleInputChange}
                  required
                  style={{ width: '100%', padding: '8px', marginTop: '4px' }}
                />
              </div>
            </div>

            <div style={{ marginBottom: '20px' }}>
              <h3>🚀 Информация о проекте</h3>

              <div style={{ marginBottom: '10px' }}>
                <label>Название проекта *</label>
                <input
                  type="text"
                  name="project_name"
                  value={formData.project_name}
                  onChange={handleInputChange}
                  required
                  style={{ width: '100%', padding: '8px', marginTop: '4px' }}
                />
              </div>

              <div style={{ marginBottom: '10px' }}>
                <label>Описание проекта *</label>
                <textarea
                  name="project_description"
                  value={formData.project_description}
                  onChange={handleInputChange}
                  required
                  rows={4}
                  style={{ width: '100%', padding: '8px', marginTop: '4px' }}
                  placeholder="Опишите суть проекта, цели, ожидаемые результаты..."
                />
              </div>

              <div style={{ display: 'flex', gap: '10px', marginBottom: '10px' }}>
                <div style={{ flex: 1 }}>
                  <label>Запрашиваемая сумма (тенге) *</label>
                  <input
                    type="number"
                    name="requested_amount"
                    value={formData.requested_amount}
                    onChange={handleInputChange}
                    required
                    min="0"
                    style={{ width: '100%', padding: '8px', marginTop: '4px' }}
                  />
                </div>

                <div style={{ flex: 1 }}>
                  <label>Срок проекта (месяцев) *</label>
                  <input
                    type="number"
                    name="project_duration_months"
                    value={formData.project_duration_months}
                    onChange={handleInputChange}
                    required
                    min="1"
                    max="120"
                    style={{ width: '100%', padding: '8px', marginTop: '4px' }}
                  />
                </div>
              </div>
            </div>

            <div style={{ marginBottom: '20px' }}>
              <h3>💰 Финансовая информация (опционально)</h3>

              <div style={{ display: 'flex', gap: '10px', marginBottom: '10px' }}>
                <div style={{ flex: 1 }}>
                  <label>Годовая выручка (тенге)</label>
                  <input
                    type="number"
                    name="annual_revenue"
                    value={formData.annual_revenue || ''}
                    onChange={handleInputChange}
                    min="0"
                    style={{ width: '100%', padding: '8px', marginTop: '4px' }}
                  />
                </div>

                <div style={{ flex: 1 }}>
                  <label>Чистая прибыль (тенге)</label>
                  <input
                    type="number"
                    name="net_profit"
                    value={formData.net_profit || ''}
                    onChange={handleInputChange}
                    style={{ width: '100%', padding: '8px', marginTop: '4px' }}
                  />
                </div>
              </div>

              <div style={{ display: 'flex', gap: '10px', marginBottom: '10px' }}>
                <div style={{ flex: 1 }}>
                  <label>Общие активы (тенге)</label>
                  <input
                    type="number"
                    name="total_assets"
                    value={formData.total_assets || ''}
                    onChange={handleInputChange}
                    min="0"
                    style={{ width: '100%', padding: '8px', marginTop: '4px' }}
                  />
                </div>

                <div style={{ flex: 1 }}>
                  <label>Общая задолженность (тенге)</label>
                  <input
                    type="number"
                    name="debt_amount"
                    value={formData.debt_amount || ''}
                    onChange={handleInputChange}
                    min="0"
                    style={{ width: '100%', padding: '8px', marginTop: '4px' }}
                  />
                </div>
              </div>
            </div>

            <button
              type="submit"
              style={{
                backgroundColor: '#4CAF50',
                color: 'white',
                padding: '12px 24px',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer',
                fontSize: '16px',
                width: '100%'
              }}
            >
              🚀 Подать заявку
            </button>
          </form>
        </main>
      </div>
    );
  }

  if (currentView === 'status') {
    return (
      <div className="App">
        <header className="App-header">
          <h1>⏳ Обработка заявки</h1>
          <p>ID заявки: {applicationId}</p>
        </header>

        <main style={{ padding: '20px', maxWidth: '1000px', margin: '0 auto' }}>
          {status && (
            <div style={{ marginBottom: '20px' }}>
              <h2>📊 Текущий статус</h2>
              <div style={{
                backgroundColor: '#f5f5f5',
                padding: '20px',
                borderRadius: '8px',
                marginBottom: '20px'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span><strong>Этап:</strong> {status.current_step}</span>
                  <span><strong>Прогресс:</strong> {status.progress_percentage}%</span>
                </div>

                <div style={{
                  width: '100%',
                  backgroundColor: '#ddd',
                  borderRadius: '10px',
                  height: '20px',
                  margin: '10px 0'
                }}>
                  <div style={{
                    width: `${status.progress_percentage}%`,
                    backgroundColor: '#4CAF50',
                    height: '100%',
                    borderRadius: '10px',
                    transition: 'width 0.3s ease'
                  }}></div>
                </div>

                <p><strong>Описание:</strong> {status.summary}</p>
              </div>
            </div>
          )}

          {reasoning.length > 0 && (
            <div>
              <h2>🤖 Рассуждения агентов</h2>
              {reasoning.map((agent, index) => (
                <div key={index} style={{
                  backgroundColor: '#f9f9f9',
                  border: '1px solid #ddd',
                  borderRadius: '8px',
                  padding: '15px',
                  marginBottom: '15px'
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <h3 style={{ margin: '0 0 10px 0', color: '#333' }}>
                      {agent.agent === 'validator' ? '📝 Валидатор' :
                       agent.agent === 'legal_checker' ? '⚖️ Юридический анализ' :
                       agent.agent === 'risk_manager' ? '⚠️ Риск-менеджер' :
                       agent.agent === 'relevance_checker' ? '🎯 Анализ актуальности' :
                       agent.agent === 'financial_analyzer' ? '💰 Финансовый анализ' :
                       agent.agent === 'decision_maker' ? '🏆 Принятие решения' :
                       agent.agent}
                    </h3>
                    {agent.confidence && (
                      <span style={{
                        backgroundColor: agent.confidence > 0.7 ? '#4CAF50' : agent.confidence > 0.5 ? '#FF9800' : '#f44336',
                        color: 'white',
                        padding: '4px 8px',
                        borderRadius: '4px',
                        fontSize: '12px'
                      }}>
                        Уверенность: {(agent.confidence * 100).toFixed(0)}%
                      </span>
                    )}
                  </div>

                  <div style={{
                    whiteSpace: 'pre-line',
                    lineHeight: '1.6',
                    fontSize: '14px'
                  }}>
                    {agent.reasoning}
                  </div>

                  <div style={{
                    fontSize: '12px',
                    color: '#666',
                    marginTop: '10px'
                  }}>
                    {new Date(agent.timestamp).toLocaleString('ru-RU')}
                  </div>
                </div>
              ))}
            </div>
          )}

          <div style={{ textAlign: 'center', marginTop: '20px' }}>
            <button
              onClick={() => {
                fetchStatus();
                fetchReasoning();
              }}
              style={{
                backgroundColor: '#2196F3',
                color: 'white',
                padding: '10px 20px',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer',
                marginRight: '10px'
              }}
            >
              🔄 Обновить
            </button>

            <button
              onClick={() => {
                setCurrentView('form');
                setApplicationId('');
                setStatus(null);
                setReasoning([]);
                if (ws) ws.close();
              }}
              style={{
                backgroundColor: '#757575',
                color: 'white',
                padding: '10px 20px',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer'
              }}
            >
              ← Новая заявка
            </button>
          </div>
        </main>
      </div>
    );
  }

  if (currentView === 'result' && finalDecision) {
    return (
      <div className="App">
        <header className="App-header">
          <h1>
            {finalDecision.status === 'approved' ? '✅ Заявка одобрена!' :
             finalDecision.status === 'conditional_approval' ? '⚠️ Условное одобрение' :
             finalDecision.status === 'requires_review' ? '🔍 Требует рассмотрения' :
             '❌ Заявка отклонена'}
          </h1>
          <p>ID заявки: {applicationId}</p>
        </header>

        <main style={{ padding: '20px', maxWidth: '800px', margin: '0 auto', textAlign: 'left' }}>
          <div style={{
            backgroundColor: finalDecision.status === 'approved' ? '#e8f5e8' :
                           finalDecision.status === 'rejected' ? '#ffeaea' : '#fff3cd',
            border: `2px solid ${finalDecision.status === 'approved' ? '#4CAF50' : 
                                finalDecision.status === 'rejected' ? '#f44336' : '#FF9800'}`,
            borderRadius: '8px',
            padding: '20px',
            marginBottom: '20px'
          }}>
            <h2>🏆 Итоговое решение</h2>

            <div style={{ marginBottom: '15px' }}>
              <strong>Статус:</strong> {
                finalDecision.status === 'approved' ? 'Одобрено' :
                finalDecision.status === 'conditional_approval' ? 'Условное одобрение' :
                finalDecision.status === 'requires_review' ? 'Требует дополнительного рассмотрения' :
                'Отклонено'
              }
            </div>

            {finalDecision.amount_approved && (
              <div style={{ marginBottom: '15px' }}>
                <strong>Одобренная сумма:</strong> {finalDecision.amount_approved.toLocaleString('ru-RU')} тенге
              </div>
            )}

            <div style={{ marginBottom: '15px' }}>
              <strong>Уровень риска:</strong> {
                finalDecision.risk_level === 'low' ? '🟢 Низкий' :
                finalDecision.risk_level === 'moderate' ? '🟡 Умеренный' :
                finalDecision.risk_level === 'high' ? '🟠 Высокий' :
                '🔴 Критический'
              }
            </div>

            <div style={{ marginBottom: '15px' }}>
              <strong>Уверенность в решении:</strong> {(finalDecision.confidence * 100).toFixed(1)}%
            </div>
          </div>

          {finalDecision.conditions.length > 0 && (
            <div style={{ marginBottom: '20px' }}>
              <h3>📜 Условия кредитования</h3>
              <ul>
                {finalDecision.conditions.map((condition, index) => (
                  <li key={index} style={{ marginBottom: '5px' }}>{condition}</li>
                ))}
              </ul>
            </div>
          )}

          <div style={{ marginBottom: '20px' }}>
            <h3>📋 Обоснование решения</h3>
            <div style={{
              backgroundColor: '#f5f5f5',
              padding: '15px',
              borderRadius: '4px',
              whiteSpace: 'pre-line',
              lineHeight: '1.6'
            }}>
              {finalDecision.reasoning}
            </div>
          </div>

          <div style={{ textAlign: 'center' }}>
            <button
              onClick={() => {
                setCurrentView('form');
                setApplicationId('');
                setStatus(null);
                setReasoning([]);
                setFinalDecision(null);
                if (ws) ws.close();
              }}
              style={{
                backgroundColor: '#4CAF50',
                color: 'white',
                padding: '12px 24px',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer',
                fontSize: '16px'
              }}
            >
              🆕 Подать новую заявку
            </button>
          </div>
        </main>
      </div>
    );
  }

  return null;
}

export default App;