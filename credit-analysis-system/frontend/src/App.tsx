import React from 'react';
import './App.css';

function App() {
  return (
    <div className="App">
      <header className="App-header">
        <h1>Credit Analysis System</h1>
        <p>Мультиагентная система рассмотрения кредитных заявок</p>
        <div>
          <h2>Статус системы</h2>
          <ul>
            <li>✅ Frontend: Запущен</li>
            <li>🔄 Backend: Подключение...</li>
            <li>🔄 База данных: Инициализация...</li>
          </ul>
        </div>
      </header>
    </div>
  );
}

export default App;