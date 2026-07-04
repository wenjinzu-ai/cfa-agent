export interface ChatRequest {
  message: string;
  session_id: string;
  stream?: boolean;
}

export interface ChatResponse {
  session_id: string;
  reply: string;
  plan_id: string | null;
  steps_executed: number;
  token_usage: { prompt: number; completion: number; total: number };
}

export interface StreamEventData {
  event_type: string;
  event_category: string | null;
  plan_id: string | null;
  step_id: number | null;
  content: string;
  timestamp: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  thinking: string;
  timestamp: Date;
  steps?: number;
  planId?: string;
  isStreaming?: boolean;
  isThinking?: boolean;
  thinkingDuration?: number;
  streamEvents?: StreamEventData[];
}

const API_BASE = '/api/v1';

export async function sendMessage(request: ChatRequest): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function* sendStreamMessage(
  request: ChatRequest
): AsyncGenerator<StreamEventData> {
  const res = await fetch(`${API_BASE}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...request, stream: true }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }

  const reader = res.body?.getReader();
  if (!reader) throw new Error('No response body');

  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (line.startsWith('data:')) {
        const data = line.slice(5).trim();
        if (data === '[DONE]') return;
        try {
          const event: StreamEventData = JSON.parse(data);
          yield event;
        } catch {
          // skip malformed
        }
      }
    }
  }
}