import { useState, useRef, type ChangeEvent, type KeyboardEvent } from 'react';
import { Send, Square } from 'lucide-react';

interface Props {
  onSend: (message: string) => void;
  loading: boolean;
}

export function ChatInput({ onSend, loading }: Props) {
  const [input, setInput] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSend = () => {
    const trimmed = input.trim();
    if (!trimmed || loading) return;
    onSend(trimmed);
    setInput('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 200) + 'px';
  };

  return (
    <div className="border-t border-border p-4">
      <div className="max-w-3xl mx-auto">
        <div className="glass-light border border-border rounded-2xl flex items-end gap-2 px-4 py-2 focus-within:border-primary/50 transition-colors">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            placeholder="输入消息... (Enter 发送, Shift+Enter 换行)"
            rows={1}
            className="flex-1 bg-transparent border-none outline-none resize-none text-sm text-text placeholder:text-text-muted py-1.5 leading-relaxed max-h-[200px]"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || loading}
            className={`flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center transition-all ${
              input.trim() && !loading
                ? 'bg-primary hover:bg-primary-dark text-white shadow-lg shadow-primary/25'
                : 'bg-surface-3 text-text-muted cursor-not-allowed'
            }`}
          >
            {loading ? (
              <Square className="w-3.5 h-3.5" />
            ) : (
              <Send className="w-3.5 h-3.5" />
            )}
          </button>
        </div>
        <p className="text-center text-[10px] text-text-muted mt-2">
          CFA-Agent · 基于意图识别的智能对话系统
        </p>
      </div>
    </div>
  );
}