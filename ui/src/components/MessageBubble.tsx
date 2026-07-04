import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Message, StreamEventData } from '../api';
import {
  ChevronRight,
  ListChecks,
  Lightbulb,
  Eye,
  AlertCircle,
  Loader2,
} from 'lucide-react';

function ThinkingStepIcon({ event }: { event: StreamEventData }) {
  switch (event.event_type) {
    case 'plan_update':
      return <ListChecks className="w-3.5 h-3.5 text-accent-blue flex-shrink-0 mt-0.5" />;
    case 'thought':
      return <Lightbulb className="w-3.5 h-3.5 text-primary-light flex-shrink-0 mt-0.5" />;
    case 'observation':
      return <Eye className="w-3.5 h-3.5 text-accent-green flex-shrink-0 mt-0.5" />;
    case 'error':
      return <AlertCircle className="w-3.5 h-3.5 text-accent-red flex-shrink-0 mt-0.5" />;
    default:
      return null;
  }
}

function ThinkingStepContent({ event }: { event: StreamEventData }) {
  const isError = event.event_type === 'error';
  const isObservation = event.event_type === 'observation';
  const isPlan = event.event_type === 'plan_update';

  let label = '';
  if (event.event_type === 'thought' && event.step_id != null) {
    label = `Step ${event.step_id}: `;
  } else if (isPlan) {
    label = 'Plan: ';
  }

  return (
    <div className={`flex items-start gap-2 ${isObservation ? 'ml-4' : ''}`}>
      <ThinkingStepIcon event={event} />
      <span
        className={`text-xs leading-relaxed ${
          isError
            ? 'text-accent-red'
            : isObservation
              ? 'text-text-muted line-clamp-3'
              : 'text-text-secondary'
        }`}
      >
        {label}
        {event.content}
      </span>
    </div>
  );
}

function ThinkingSection({
  message,
}: {
  message: Message;
}) {
  const [open, setOpen] = useState(true);
  const thinkingEvents = (message.streamEvents || []).filter(
    (e) => e.event_type !== 'answer' && e.event_type !== 'result'
  );

  if (thinkingEvents.length === 0 && !message.thinking) return null;

  const stepCount = thinkingEvents.filter((e) => e.event_type === 'thought').length;

  return (
    <div className="mb-3">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 text-xs text-text-muted hover:text-text-secondary transition-colors group"
      >
        <ChevronRight
          className={`w-3.5 h-3.5 transition-transform duration-200 ${
            open ? 'rotate-90' : ''
          }`}
        />
        {message.isThinking ? (
          <span className="flex items-center gap-1.5">
            <Loader2 className="w-3 h-3 animate-spin-smooth text-primary-light" />
            <span className="text-primary-light">思考中...</span>
          </span>
        ) : (
          <span>思考过程</span>
        )}
        {stepCount > 0 && (
          <span className="px-1.5 py-0.5 rounded bg-surface-2 text-text-muted text-[10px]">
            {stepCount}步
          </span>
        )}
        {message.thinkingDuration != null && message.thinkingDuration > 0 && (
          <span className="text-[10px] text-text-muted">
            {message.thinkingDuration}s
          </span>
        )}
        {message.planId && (
          <span className="px-1.5 py-0.5 rounded text-[10px] bg-accent-blue/10 text-accent-blue">
            Plan
          </span>
        )}
      </button>

      {open && (
        <div className="mt-2 ml-1 pl-3 border-l-2 border-primary/20 space-y-1.5">
          {thinkingEvents.length > 0
            ? thinkingEvents.map((event, i) => (
                <ThinkingStepContent
                  key={`${message.id}-te-${i}`}
                  event={event}
                />
              ))
            : message.thinking.split('\n').map((line, i) => (
                <div key={`${message.id}-tl-${i}`} className="text-xs text-text-muted">
                  {line}
                </div>
              ))}
          {message.isThinking && (
            <div className="flex items-center gap-1.5 py-1">
              <Loader2 className="w-3 h-3 animate-spin-smooth text-primary-light" />
              <span className="text-[10px] text-text-muted">正在执行...</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function cleanReply(content: string): string {
  let text = content;
  const faIdx = text.indexOf('Final Answer:');
  if (faIdx !== -1) {
    text = text.slice(faIdx + 'Final Answer:'.length).trim();
  }
  return text;
}

export function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === 'user';
  const hasThinking = !isUser && (message.thinking || (message.streamEvents || []).length > 0);
  const displayContent = isUser ? message.content : cleanReply(message.content);

  return (
    <div className={`animate-fade-in flex ${isUser ? 'justify-end' : 'justify-start'} mb-6`}>
      <div className={`flex gap-3 max-w-[85%] ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
        <div
          className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ${
            isUser
              ? 'bg-primary/20 text-primary-light'
              : 'bg-gradient-to-br from-primary to-primary-dark text-white'
          }`}
        >
          {isUser ? 'U' : 'AI'}
        </div>

        <div className="flex flex-col gap-1.5 min-w-0">
          {hasThinking && <ThinkingSection message={message} />}

          <div
            className={`rounded-2xl px-4 py-3 ${
              isUser
                ? 'bg-primary text-white rounded-br-md'
                : 'glass border border-border rounded-bl-md'
            }`}
          >
            {message.isStreaming && !displayContent ? (
              <div className="flex items-center gap-1.5 py-1">
                <div className="typing-dot w-2 h-2 rounded-full bg-primary-light" />
                <div className="typing-dot w-2 h-2 rounded-full bg-primary-light" />
                <div className="typing-dot w-2 h-2 rounded-full bg-primary-light" />
              </div>
            ) : isUser ? (
              <p className="whitespace-pre-wrap text-sm leading-relaxed">{displayContent}</p>
            ) : (
              <div className={`markdown-body text-sm ${message.isStreaming ? 'streaming-cursor' : ''}`}>
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {displayContent}
                </ReactMarkdown>
              </div>
            )}
          </div>

          {!isUser && !message.isStreaming && message.steps !== undefined && message.steps > 0 && (
            <div className="flex items-center gap-2 text-[10px] text-text-muted px-1">
              <span>{message.steps} 步骤</span>
              {message.planId && <span>· Plan: {message.planId.slice(0, 8)}</span>}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}