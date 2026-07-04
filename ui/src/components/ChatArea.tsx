import { useEffect, useRef } from 'react';
import type { Message } from '../api';
import { MessageBubble } from './MessageBubble';
import { Sparkles } from 'lucide-react';

interface Props {
  messages: Message[];
  suggestion: string | null;
  onSuggestionConsumed: () => void;
  onSuggestion: (text: string) => void;
}

const SUGGESTIONS = [
  '你好，介绍一下你自己',
  'Python的GIL是什么？',
  '帮我搜索Python异步编程的最佳实践',
  '对比REST和GraphQL的优缺点',
];

export function ChatArea({ messages, suggestion, onSuggestionConsumed, onSuggestion }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const prevMessageCount = useRef(messages.length);

  useEffect(() => {
    if (messages.length > prevMessageCount.current) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
    prevMessageCount.current = messages.length;
  }, [messages.length]);

  useEffect(() => {
    if (suggestion) {
      onSuggestionConsumed();
    }
  }, [suggestion, onSuggestionConsumed]);

  if (messages.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center px-6">
        <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-primary to-primary-dark flex items-center justify-center shadow-2xl shadow-primary/20 mb-6">
          <Sparkles className="w-8 h-8 text-white" />
        </div>
        <h2 className="text-xl font-semibold text-text mb-2">CFA-Agent</h2>
        <p className="text-sm text-text-muted mb-8 text-center max-w-md">
          基于意图识别的智能对话系统，支持简单问答直接回复和复杂任务规划执行
        </p>
        <div className="grid grid-cols-2 gap-3 w-full max-w-lg">
          {SUGGESTIONS.map((s, i) => (
            <button
              key={i}
              className="text-left px-4 py-3 rounded-xl border border-border hover:border-primary/40 hover:bg-primary/5 text-sm text-text-secondary hover:text-text transition-all"
              onClick={() => onSuggestion(s)}
            >
              <span className="text-primary-light mr-1.5">→</span>
              {s}
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6">
      <div className="max-w-3xl mx-auto">
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}