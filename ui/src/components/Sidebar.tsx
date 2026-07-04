import { useMemo } from 'react';
import { Sparkles, Trash2, MessageSquare } from 'lucide-react';
import type { Message } from '../api';

interface Props {
  messages: Message[];
  onClear: () => void;
}

export function Sidebar({ messages, onClear }: Props) {
  const userCount = useMemo(
    () => messages.filter((m) => m.role === 'user').length,
    [messages]
  );
  const planCount = useMemo(
    () => messages.filter((m) => m.steps && m.steps > 0).length,
    [messages]
  );
  const userMessages = useMemo(
    () => messages.filter((m) => m.role === 'user'),
    [messages]
  );

  return (
    <aside className="w-64 flex-shrink-0 glass border-r border-border flex flex-col h-screen">
      <div className="p-5 border-b border-border">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-primary to-primary-dark flex items-center justify-center shadow-lg shadow-primary/20">
            <Sparkles className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-sm font-semibold text-text">CFA-Agent</h1>
            <p className="text-[10px] text-text-muted">智能对话系统</p>
          </div>
        </div>
      </div>

      <div className="p-3">
        <button
          onClick={onClear}
          className="w-full flex items-center gap-2 px-3 py-2.5 rounded-xl border border-border hover:border-primary/40 hover:bg-primary/5 text-text-secondary hover:text-text transition-all text-sm"
        >
          <MessageSquare className="w-4 h-4" />
          新对话
        </button>
      </div>

      <div className="px-5 py-3 border-t border-border">
        <h3 className="text-[10px] uppercase tracking-wider text-text-muted mb-3">会话信息</h3>
        <div className="space-y-2">
          <div className="flex justify-between text-xs">
            <span className="text-text-muted">消息数</span>
            <span className="text-text-secondary">{messages.length}</span>
          </div>
          <div className="flex justify-between text-xs">
            <span className="text-text-muted">对话轮次</span>
            <span className="text-text-secondary">{userCount}</span>
          </div>
          <div className="flex justify-between text-xs">
            <span className="text-text-muted">规划执行</span>
            <span className="text-accent-blue">{planCount} 次</span>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-2">
        <h3 className="text-[10px] uppercase tracking-wider text-text-muted mb-2 px-2">历史消息</h3>
        <div className="space-y-0.5">
          {userMessages.map((m) => (
            <div
              key={m.id}
              className="px-2 py-1.5 rounded-lg text-xs text-text-muted truncate hover:bg-surface-3 hover:text-text-secondary transition-colors cursor-default"
            >
              {m.content}
            </div>
          ))}
        </div>
      </div>

      <div className="p-3 border-t border-border">
        <button
          onClick={onClear}
          className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs text-text-muted hover:text-accent-red hover:bg-accent-red/5 transition-all"
        >
          <Trash2 className="w-3.5 h-3.5" />
          清空对话
        </button>
      </div>
    </aside>
  );
}