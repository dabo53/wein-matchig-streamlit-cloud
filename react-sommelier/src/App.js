import React, { useState, useRef, useEffect } from 'react';
import './index.css';

// SVG Icons
const WineGlassIcon = () => (
  <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
    <path d="M6 2h12v7c0 3.31-2.69 6-6 6s-6-2.69-6-6V2zm6 11c2.21 0 4-1.79 4-4V4H8v5c0 2.21 1.79 4 4 4zm-1 3.93V20H8v2h8v-2h-3v-3.07c3.39-.49 6-3.39 6-6.93V0H5v9c0 3.54 2.61 6.44 6 6.93z"/>
  </svg>
);

const ArrowIcon = () => (
  <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
    <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
  </svg>
);

const PlusIcon = () => (
  <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
    <path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/>
  </svg>
);

// Wine Card Component
const WineCard = ({ wine }) => (
  <div className="wine-card">
    <div className="wine-card-header">
      <span className="wine-name">{wine.name}</span>
      <span className="wine-badge">{wine.points} Pkt</span>
    </div>
    <div className="wine-meta">{wine.region} · {wine.grape}</div>
    <div className="wine-description">{wine.description}</div>
    <div className="wine-footer">
      <span className="wine-price">{wine.price}</span>
      <button className="wine-button">Mehr Details</button>
    </div>
  </div>
);

// Message Component
const Message = ({ message }) => (
  <div className={`message ${message.sender}`}>
    {message.sender === 'bot' && <div className="message-label">Sommelier</div>}
    <div className="message-bubble">{message.text}</div>
    {message.wines && (
      <div className="wine-cards">
        {message.wines.map((wine, idx) => (
          <WineCard key={idx} wine={wine} />
        ))}
      </div>
    )}
  </div>
);

// Chat View
const ChatView = ({ messages, inputValue, setInputValue, onSend }) => {
  const chatRef = useRef(null);

  useEffect(() => {
    if (chatRef.current) {
      chatRef.current.scrollTop = chatRef.current.scrollHeight;
    }
  }, [messages]);

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && inputValue.trim()) {
      onSend();
    }
  };

  const quickActions = [
    { icon: '🍷', label: 'Rotwein' },
    { icon: '🥂', label: 'Champagner' },
    { icon: '🍽️', label: 'Speisebegleitung' },
    { icon: '📚', label: 'Weinwissen' },
  ];

  return (
    <>
      <div className="chat-container" ref={chatRef}>
        {messages.map((msg, idx) => (
          <Message key={idx} message={msg} />
        ))}
      </div>

      <div className="input-area">
        <div className="input-container">
          <input
            type="text"
            className="input-field"
            placeholder="Fragen Sie Ihren Sommelier..."
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyPress={handleKeyPress}
          />
          <button className="send-button" onClick={onSend}>
            <ArrowIcon />
          </button>
        </div>
      </div>

      <div className="quick-actions">
        {quickActions.map((action, idx) => (
          <button key={idx} className="quick-chip">
            {action.icon} {action.label}
          </button>
        ))}
      </div>
    </>
  );
};

// Profile View
const ProfileView = () => {
  const tasteProfile = [
    { label: 'Süße', value: 25 },
    { label: 'Säure', value: 70 },
    { label: 'Tannin', value: 60 },
    { label: 'Körper', value: 55 },
    { label: 'Alkohol', value: 45 },
  ];

  const preferences = ['Bordeaux', 'Burgund', 'Bio-Weine', 'unter 50€', 'Barrique'];

  return (
    <div className="profile-container">
      <div className="profile-section">
        <h3 className="profile-section-title">Geschmacksprofil</h3>
        {tasteProfile.map((item, idx) => (
          <div key={idx} className="taste-item">
            <div className="taste-label">
              <span>{item.label}</span>
              <span>{item.value}%</span>
            </div>
            <div className="taste-bar">
              <div className="taste-fill" style={{ width: `${item.value}%` }} />
            </div>
          </div>
        ))}
      </div>

      <div className="profile-section">
        <h3 className="profile-section-title">Präferenzen</h3>
        <div className="preference-tags">
          {preferences.map((pref, idx) => (
            <span key={idx} className="preference-tag">{pref}</span>
          ))}
        </div>
      </div>
    </div>
  );
};

// Cellar View
const CellarView = () => {
  const slots = [
    { filled: true }, { filled: true }, { filled: false },
    { filled: true }, { filled: false }, { filled: true },
    { filled: false }, { filled: true }, { filled: false },
  ];

  const filledCount = slots.filter(s => s.filled).length;
  const emptyCount = slots.filter(s => !s.filled).length;

  return (
    <div className="cellar-container">
      <div className="profile-section">
        <h3 className="profile-section-title">Mein Weinkeller</h3>
        <div className="cellar-grid">
          {slots.map((slot, idx) => (
            <div key={idx} className={`cellar-slot ${slot.filled ? 'filled' : 'empty'}`}>
              {slot.filled ? <WineGlassIcon /> : <PlusIcon />}
            </div>
          ))}
        </div>
        <div className="cellar-summary">
          {filledCount} Flaschen im Keller · {emptyCount} Plätze frei
        </div>
      </div>
    </div>
  );
};

// Main App
function App() {
  const [activeTab, setActiveTab] = useState('chat');
  const [inputValue, setInputValue] = useState('');
  const [messages, setMessages] = useState([
    {
      sender: 'bot',
      text: 'Guten Abend! Ich bin Ihr persönlicher Sommelier. Wie darf ich Ihnen heute behilflich sein?',
    },
    {
      sender: 'user',
      text: 'Ich suche einen Rotwein zu einem Rinderfilet.',
    },
    {
      sender: 'bot',
      text: 'Eine ausgezeichnete Wahl! Zu einem Rinderfilet empfehle ich Ihnen kräftige Rotweine mit guter Tanninstruktur. Hier sind meine Empfehlungen:',
      wines: [
        {
          name: 'Barolo DOCG 2018',
          region: 'Piemont, Italien',
          grape: 'Nebbiolo',
          points: 94,
          description: 'Die Struktur dieses Rotweins harmoniert ausgezeichnet mit der Intensität des Fleisches. Die samtigen Tannine umschmeicheln die reichhaltigen Aromen des Gerichts.',
          price: '€78',
        },
        {
          name: 'Châteauneuf-du-Pape 2019',
          region: 'Rhône, Frankreich',
          grape: 'Grenache, Syrah',
          points: 92,
          description: 'Die Fülle des Weins steht im perfekten Gleichgewicht mit der Aromatik Ihrer Speise. Dabei stehen Wein und Speise in perfekter Balance zueinander.',
          price: '€52',
        },
      ],
    },
  ]);

  const handleSend = () => {
    if (!inputValue.trim()) return;

    const newMessages = [...messages, { sender: 'user', text: inputValue }];
    setMessages(newMessages);
    setInputValue('');

    // Simulate bot response
    setTimeout(() => {
      setMessages([
        ...newMessages,
        {
          sender: 'bot',
          text: 'Vielen Dank für Ihre Anfrage. Ich analysiere gerade die besten Optionen für Sie...',
        },
      ]);
    }, 1000);
  };

  const tabs = [
    { id: 'chat', label: 'Chat' },
    { id: 'profile', label: 'Profil' },
    { id: 'cellar', label: 'Keller' },
  ];

  return (
    <div className="app">
      {/* Header */}
      <header className="header">
        <div className="header-icon">
          <WineGlassIcon />
        </div>
        <h1 className="header-title">SOMMELIER</h1>
        <p className="header-subtitle">Ihr Weinberater</p>
      </header>

      {/* Tab Navigation */}
      <nav className="tabs">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            className={`tab ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {/* Views */}
      {activeTab === 'chat' && (
        <ChatView
          messages={messages}
          inputValue={inputValue}
          setInputValue={setInputValue}
          onSend={handleSend}
        />
      )}
      {activeTab === 'profile' && <ProfileView />}
      {activeTab === 'cellar' && <CellarView />}
    </div>
  );
}

export default App;
