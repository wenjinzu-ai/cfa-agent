import { useState, useCallback } from 'react';
import { useChat } from './hooks/useChat';
import { Sidebar } from './components/Sidebar';
import { ChatArea } from './components/ChatArea';
import { ChatInput } from './components/ChatInput';

function App() {
  const { messages, loading, send, clear } = useChat();
  const [suggestion, setSuggestion] = useState<string | null>(null);

  const handleSuggestion = useCallback((text: string) => {
    setSuggestion(text);
    send(text);
  }, [send]);

  const handleSuggestionConsumed = useCallback(() => {
    setSuggestion(null);
  }, []);

  return (
    <div className="flex w-full h-screen overflow-hidden">
      <Sidebar messages={messages} onClear={clear} />
      <main className="flex-1 flex flex-col min-w-0">
        <ChatArea
          messages={messages}
          suggestion={suggestion}
          onSuggestionConsumed={handleSuggestionConsumed}
          onSuggestion={handleSuggestion}
        />
        <ChatInput onSend={send} loading={loading} />
      </main>
    </div>
  );
}

export default App;