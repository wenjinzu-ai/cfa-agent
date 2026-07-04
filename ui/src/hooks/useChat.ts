import { useState, useCallback, useRef } from 'react';
import type { Message, StreamEventData } from '../api';
import { sendStreamMessage, sendMessage } from '../api';

function genId() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}

function formatThinkingEvent(event: StreamEventData): string {
  switch (event.event_type) {
    case 'plan_update':
      return `📋 ${event.content}`;
    case 'thought':
      return `💭 ${event.content}`;
    case 'observation':
      return `👁 ${event.content}`;
    case 'error':
      return `❌ ${event.content}`;
    default:
      return event.content;
  }
}

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const sessionIdRef = useRef(genId());

  const updateAssistantMessage = useCallback(
    (assistantId: string, patch: Partial<Message>) => {
      setMessages((prev) =>
        prev.map((m): Message =>
          m.id === assistantId ? { ...m, ...patch } : m
        )
      );
    },
    []
  );

  const send = useCallback(async (content: string) => {
    const userMsg: Message = {
      id: genId(),
      role: 'user',
      content,
      thinking: '',
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    const assistantId = genId();
    const assistantMsg: Message = {
      id: assistantId,
      role: 'assistant',
      content: '',
      thinking: '',
      timestamp: new Date(),
      isStreaming: true,
      isThinking: false,
      streamEvents: [],
    };
    setMessages((prev) => [...prev, assistantMsg]);

    try {
      const events: StreamEventData[] = [];
      let answerContent = '';
      let thinkingContent = '';
      let thinkingStartTime: number | null = null;
      let thinkingDone = false;
      let updateTimer: ReturnType<typeof requestAnimationFrame> | null = null;
      let pendingPatch: Partial<Message> | null = null;

      const flushUpdate = () => {
        updateTimer = null;
        if (pendingPatch) {
          updateAssistantMessage(assistantId, pendingPatch);
          pendingPatch = null;
        }
      };

      const scheduleUpdate = (patch: Partial<Message>) => {
        pendingPatch = pendingPatch ? { ...pendingPatch, ...patch } : patch;
        if (!updateTimer) {
          updateTimer = requestAnimationFrame(flushUpdate);
        }
      };

      const finishThinking = () => {
        if (!thinkingDone) {
          thinkingDone = true;
          const duration = thinkingStartTime
            ? Math.round((Date.now() - thinkingStartTime) / 1000)
            : 0;
          scheduleUpdate({ isThinking: false, thinkingDuration: duration });
        }
      };

      for await (const event of sendStreamMessage({
        message: content,
        session_id: sessionIdRef.current,
      })) {
        events.push(event);

        if (event.event_type === 'answer') {
          finishThinking();
          answerContent += event.content;
          scheduleUpdate({ content: answerContent, streamEvents: [...events] });
        } else if (event.event_type === 'result') {
          finishThinking();
          answerContent = event.content;
          scheduleUpdate({ content: answerContent, streamEvents: [...events] });
        } else {
          if (!thinkingStartTime) thinkingStartTime = Date.now();
          thinkingContent += (thinkingContent ? '\n' : '') + formatThinkingEvent(event);
          scheduleUpdate({
            thinking: thinkingContent,
            isThinking: true,
            streamEvents: [...events],
          });
        }
      }

      if (updateTimer) {
        cancelAnimationFrame(updateTimer);
      }

      if (!answerContent) {
        const res = await sendMessage({
          message: content,
          session_id: sessionIdRef.current,
        });
        answerContent = res.reply;
      }

      const duration = thinkingStartTime
        ? Math.round((Date.now() - thinkingStartTime) / 1000)
        : 0;

      updateAssistantMessage(assistantId, {
        content: answerContent,
        thinking: thinkingContent,
        isStreaming: false,
        isThinking: false,
        thinkingDuration: duration,
        steps: events.filter((e) => e.event_type === 'thought').length,
        planId: events.find((e) => e.plan_id)?.plan_id ?? undefined,
        streamEvents: events,
      });
    } catch (err: unknown) {
      const errorMsg = err instanceof Error ? err.message : 'Unknown error';
      updateAssistantMessage(assistantId, {
        content: `⚠️ ${errorMsg}`,
        thinking: '',
        isStreaming: false,
        isThinking: false,
      });
    } finally {
      setLoading(false);
    }
  }, [updateAssistantMessage]);

  const clear = useCallback(() => {
    sessionIdRef.current = genId();
    setMessages([]);
  }, []);

  return { messages, loading, send, clear };
}