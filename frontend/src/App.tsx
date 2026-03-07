import React, { useState } from 'react';
import Items from './Items';        // импорт существующего компонента22222
import Dashboard from './Dashboard'; // наш новый компонент
import Login from './Login';         // импорт компонента логина (если есть)
import './App.css';

const App: React.FC = () => {
  const [page, setPage] = useState<'items' | 'dashboard'>('items');
  const token = localStorage.getItem('api_key');

  if (!token) {
    return <Login />;
  }

  return (
    <div>
      <header style={{ padding: '10px', borderBottom: '1px solid #ccc' }}>
        <button onClick={() => setPage('items')} disabled={page === 'items'}>
          Items
        </button>
        <button onClick={() => setPage('dashboard')} disabled={page === 'dashboard'}>
          Dashboard
        </button>
      </header>
      <main>
        {page === 'items' ? <Items /> : <Dashboard />}
      </main>
    </div>
  );
};

export default App;