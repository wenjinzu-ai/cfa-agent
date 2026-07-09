const API_BASE = '/api';

export type Agent = {
  id: string;
  role: string;
  name: string;
  status: string;
  config: Record<string, unknown> | null;
  performance_metrics: Record<string, unknown> | null;
  last_heartbeat: string | null;
  created_at: string | null;
  updated_at: string | null;
  is_system: boolean;
};

export type Task = {
  id: string;
  description: string;
  status: string;
  priority: number;
  max_iterations: number;
  iteration_count: number;
  result: Record<string, unknown> | null;
  introspection_state: string | null;
  created_at: string;
  completed_at: string | null;
};

export type TaskListResponse = {
  tasks: Task[];
  total: number;
};

export type ChatMessage = {
  role: 'user' | 'assistant';
  content: string;
  agent_name?: string;
};

export type SessionItem = {
  id: string;
  status: string;
  summary: string | null;
  last_activity_at: string | null;
  created_at: string;
};

export type Tool = {
  name: string;
  description: string;
  category: string;
  enabled: boolean;
};

export type Skill = {
  name: string;
  description: string;
  triggers: string[];
  prompt?: string;
};

export type ApiResponse<T> = {
  success: boolean;
  data: T;
  message?: string;
};

export type PaginatedData<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};

export type AgentListResponse = {
  agents: Agent[];
  total: number;
};

export type HealthCheck = {
  status: string;
  timestamp: string;
  version: string;
};

export type AppInfo = {
  name: string;
  version: string;
  status: string;
  description: string;
};

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ message: res.statusText }));
    throw new Error(err.message || `HTTP ${res.status}`);
  }
  return res.json();
}

export const api = {
  health: () => request<HealthCheck>('/health'),
  appInfo: () => request<AppInfo>('/'),

  agents: {
    list: (params?: { role?: string }) => {
      const qs = params ? '?' + new URLSearchParams(params as Record<string, string>).toString() : '';
      return request<ApiResponse<AgentListResponse>>(`/agents${qs}`);
    },
    get: (id: string) => request<ApiResponse<Agent>>(`/agents/${id}`),
    updateConfig: (id: string, config: Record<string, unknown>) =>
      request<ApiResponse<Agent>>(`/agents/${id}/config`, { method: 'PUT', body: JSON.stringify({ config }) }),
    updateStatus: (id: string, status: string) =>
      request<ApiResponse<Agent>>(`/agents/${id}/status?status=${status}`, { method: 'PUT' }),
  },

  tasks: {
    list: (params?: { status?: string; limit?: number }) => {
      const qs = params ? '?' + new URLSearchParams(params as Record<string, string>).toString() : '';
      return request<ApiResponse<TaskListResponse>>(`/tasks${qs}`);
    },
    get: (id: string) => request<ApiResponse<Task>>(`/tasks/${id}`),
    cancel: (id: string) =>
      request<ApiResponse<Task>>(`/tasks/${id}/cancel`, { method: 'POST' }),
  },

  tools: {
    list: () => request<ApiResponse<Tool[]>>('/tools'),
    get: (name: string) => request<ApiResponse<Tool>>(`/tools/${name}`),
    schemas: () => request<ApiResponse<Record<string, unknown>[]>>('/tools/schemas/functions'),
  },

  skills: {
    list: () => request<ApiResponse<Skill[]>>('/skills'),
    get: (name: string) => request<ApiResponse<Skill>>(`/skills/${name}`),
  },

  mcp: {
    servers: () => request<ApiResponse<Record<string, unknown>[]>>('/mcp/servers'),
    connect: (name: string) =>
      request<ApiResponse<null>>(`/mcp/servers/${name}/connect`, { method: 'POST' }),
    disconnect: (name: string) =>
      request<ApiResponse<null>>(`/mcp/servers/${name}/disconnect`, { method: 'POST' }),
  },

  chat: {
    stream: (data: { message: string; session_id?: string; agent_id?: string; max_steps?: number; temperature?: number; max_tokens?: number }) => {
      return fetch(`${API_BASE}/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
    },
    getHistory: (sessionId: string) =>
      request<ApiResponse<{ session_id: string; history: ChatMessage[] }>>(`/chat/sessions/${sessionId}/history`),
    listSessions: (limit?: number) =>
      request<ApiResponse<{ sessions: SessionItem[]; total: number }>>(`/chat/sessions${limit ? `?limit=${limit}` : ''}`),
  },
};