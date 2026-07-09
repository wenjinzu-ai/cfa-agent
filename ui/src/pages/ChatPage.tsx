import { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { Send, Bot, User, Loader2, Wrench, Plus, MessageSquare, PanelLeftClose, PanelLeft, Sparkles, ChevronDown, ChevronRight, ArrowRight } from 'lucide-react';
import { api, type SessionItem } from '../lib/api';
import AgentStatusPanel from '../components/AgentStatusPanel';

type ThinkingStep = {
  step: number;
  agent: string;
  content: string;
  toolName?: string;
  toolArgs?: Record<string, unknown>;
  observation?: string;
  isHandoff?: boolean;
  handoffTo?: string;
  handoffTask?: string;
};

type Message = {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: number;
  agentName?: string;
  steps?: number;
  durationMs?: number;
  thinkingSteps: ThinkingStep[];
};

const SUGGESTIONS = [
  { icon: '💡', label: '帮我分析一个技术方案的优劣' },
  { icon: '📊', label: '搜索最新的多智能体架构实践' },
  { icon: '🔧', label: '帮我规划一个项目的开发步骤' },
  { icon: '📝', label: '总结一下当前系统的架构设计' },
];

const AGENT_LABELS: Record<string, string> = {
  supervisor: '监督者',
  planner: '规划者',
  executor: '执行者',
  reviewer: '审查者',
};

function getAgentLabel(agentId: string) {
  return AGENT_LABELS[agentId] || agentId;
}

async function parseSSEStream(
  response: Response,
  onEvent: (event: Record<string, unknown>) => void,
  onDone: () => void,
  onError: (err: Error) => void,
) {
  const reader = response.body?.getReader();
  if (!reader) {
    onError(new Error('响应流不可读'));
    return;
  }

  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith('data: ')) continue;

        const data = trimmed.slice(6);
        if (data === '[DONE]') {
          onDone();
          return;
        }

        try {
          const parsed = JSON.parse(data);
          onEvent(parsed);
        } catch {
          // skip
        }
      }
    }
    onDone();
  } catch (err) {
    onError(err instanceof Error ? err : new Error(String(err)));
  }
}

const SESSION_KEY = 'cfa-session-id';

function groupSessionsByTime(sessions: SessionItem[]) {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const yesterday = today - 86400000;
  const week = today - 7 * 86400000;

  const groups: { label: string; items: SessionItem[] }[] = [
    { label: '今天', items: [] },
    { label: '昨天', items: [] },
    { label: '近7天', items: [] },
    { label: '更早', items: [] },
  ];

  for (const s of sessions) {
    const t = new Date(s.created_at || s.last_activity_at || Date.now()).getTime();
    if (t >= today) groups[0].items.push(s);
    else if (t >= yesterday) groups[1].items.push(s);
    else if (t >= week) groups[2].items.push(s);
    else groups[3].items.push(s);
  }

  return groups.filter(g => g.items.length > 0);
}

function ThinkingSection({ steps, loading }: { steps: ThinkingStep[]; loading: boolean }) {
  const [expanded, setExpanded] = useState(true);

  if (steps.length === 0 && !loading) return null;

  const lastStep = steps[steps.length - 1];
  const summary = loading
    ? lastStep
      ? `${getAgentLabel(lastStep.agent)}: ${lastStep.content.slice(0, 60)}${lastStep.content.length > 60 ? '...' : ''}`
      : '思考中...'
    : `${steps.length} 个步骤`;

  return (
    <div className="mb-2">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-300 transition-colors group"
      >
        {expanded ? (
          <ChevronDown className="w-3 h-3" />
        ) : (
          <ChevronRight className="w-3 h-3" />
        )}
        <span className="text-zinc-400/70">
          {loading ? '思考中' : `思考过程`}
        </span>
        <span className="text-zinc-600">· {summary}</span>
      </button>

      {expanded && (
        <div className="mt-1.5 ml-1 border-l-2 border-cfa-500/20 pl-3 space-y-1.5">
          {steps.map((s, i) => (
            <div key={i} className="text-[11px] leading-relaxed">
              {s.isHandoff ? (
                <div className="flex items-center gap-1.5 text-cfa-400/80">
                  <ArrowRight className="w-3 h-3" />
                  <span>委派给 <span className="text-cfa-300">{getAgentLabel(s.handoffTo || '')}</span></span>
                  {s.handoffTask && <span className="text-zinc-600 ml-1">— {s.handoffTask.slice(0, 50)}</span>}
                </div>
              ) : s.toolName === 'delegate' ? (
                <div className="flex items-center gap-1.5 text-cfa-400/80">
                  <ArrowRight className="w-3 h-3" />
                  <span className="text-zinc-500">{getAgentLabel(s.agent)}</span>
                  <span>委派给 <span className="text-cfa-300">{getAgentLabel((s.toolArgs as Record<string, string>)?.role || '')}</span></span>
                  {(s.toolArgs as Record<string, string>)?.task && (
                    <span className="text-zinc-600 ml-1 truncate max-w-[200px]">
                      — {(s.toolArgs as Record<string, string>).task.slice(0, 50)}
                    </span>
                  )}
                </div>
              ) : s.toolName ? (
                <div className="flex items-center gap-1.5 text-zinc-400">
                  <Wrench className="w-3 h-3 text-cfa-500/60" />
                  <span className="text-zinc-500">{getAgentLabel(s.agent)}</span>
                  <span className="px-1.5 py-0.5 bg-cfa-500/10 rounded text-cfa-400/70">{s.toolName}</span>
                  {s.observation && (
                    <span className="text-zinc-600 truncate max-w-[200px]">{s.observation.slice(0, 80)}</span>
                  )}
                </div>
              ) : s.observation ? (
                <div className="flex items-start gap-1.5 text-zinc-500">
                  <Wrench className="w-3 h-3 text-zinc-600 shrink-0 mt-0.5" />
                  <span className="text-zinc-500">{getAgentLabel(s.agent)}</span>
                  <span className="text-zinc-600 line-clamp-2">{s.observation.slice(0, 100)}</span>
                </div>
              ) : (
                <div className="text-zinc-500">
                  <span className="text-zinc-600">{getAgentLabel(s.agent)}</span>
                  {' '}
                  {s.content.slice(0, 100)}{s.content.length > 100 ? '...' : ''}
                </div>
              )}
            </div>
          ))}
          {loading && (
            <div className="flex items-center gap-1.5 text-zinc-600 text-[11px]">
              <div className="flex gap-0.5">
                <span className="w-1 h-1 bg-cfa-400/50 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-1 h-1 bg-cfa-400/50 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-1 h-1 bg-cfa-400/50 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
              执行中...
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(() => localStorage.getItem(SESSION_KEY));
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [agentPanelOpen, setAgentPanelOpen] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const streamIdRef = useRef<string | null>(null);

  const hasMessages = messages.length > 0;

  const activeThinkingSteps = useMemo(() => {
    if (!streamIdRef.current) return [];
    const activeMsg = messages.find(m => m.id === streamIdRef.current);
    return activeMsg?.thinkingSteps || [];
  }, [messages]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    if (sessionId) {
      loadHistory(sessionId);
    }
    loadSessions();
  }, []);

  const loadSessions = useCallback(async () => {
    try {
      const res = await api.chat.listSessions(50);
      setSessions(res.data.sessions || []);
    } catch {
      // ignore
    }
  }, []);

  const loadHistory = useCallback(async (sid: string) => {
    try {
      const res = await api.chat.getHistory(sid);
      const history = res.data.history || [];
      if (history.length === 0) {
        setMessages([]);
        return;
      }
      const restored: Message[] = history.map((m, i) => ({
        id: `hist-${i}`,
        role: m.role,
        content: m.content,
        timestamp: Date.now() - (history.length - i) * 60000,
        agentName: m.agent_name,
        thinkingSteps: [],
      }));
      setMessages(restored);
    } catch {
      setMessages([]);
    }
  }, []);

  const handleNewChat = () => {
    setSessionId(null);
    localStorage.removeItem(SESSION_KEY);
    setMessages([]);
    setInput('');
    loadSessions();
    inputRef.current?.focus();
  };

  const handleSelectSession = async (sid: string) => {
    setSessionId(sid);
    localStorage.setItem(SESSION_KEY, sid);
    await loadHistory(sid);
  };

  const handleSend = async (overrideText?: string) => {
    const text = (overrideText || input).trim();
    if (!text || loading) return;

    const userMsg: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: text,
      timestamp: Date.now(),
      thinkingSteps: [],
    };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    const assistantId = `stream-${Date.now()}`;
    streamIdRef.current = assistantId;

    const assistantMsg: Message = {
      id: assistantId,
      role: 'assistant',
      content: '',
      timestamp: Date.now(),
      thinkingSteps: [],
    };
    setMessages(prev => [...prev, assistantMsg]);

    try {
      const response = await api.chat.stream({
        message: text,
        session_id: sessionId || undefined,
        agent_id: 'supervisor',
        max_steps: 10,
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({ message: '请求失败' }));
        throw new Error(errData.message || `HTTP ${response.status}`);
      }

      let fullContent = '';
      const thinkingSteps: ThinkingStep[] = [];
      let agentName = '';

      await parseSSEStream(
        response,
        (event) => {
          const type = event.type as string;

          if (type === 'token') {
            fullContent += (event.content as string) || '';
            setMessages(prev =>
              prev.map(m =>
                m.id === assistantId ? { ...m, content: fullContent } : m,
              ),
            );
          } else if (type === 'start') {
            agentName = (event.agent_name as string) || '';
            const sid = event.session_id as string | undefined;
            if (sid && !sessionId) {
              setSessionId(sid);
              localStorage.setItem(SESSION_KEY, sid);
            }
            setMessages(prev =>
              prev.map(m =>
                m.id === assistantId ? { ...m, agentName } : m,
              ),
            );
          } else if (type === 'thinking') {
            thinkingSteps.push({
              step: event.step as number,
              agent: (event.agent as string) || 'supervisor',
              content: (event.content as string) || '',
            });
            setMessages(prev =>
              prev.map(m =>
                m.id === assistantId ? { ...m, thinkingSteps: [...thinkingSteps] } : m,
              ),
            );
          } else if (type === 'step') {
            const stepAgent = (event.agent as string) || 'supervisor';
            const stepToolName = event.tool_name as string | undefined;
            const stepObservation = event.observation as string | undefined;

            if (stepToolName && stepToolName !== 'delegate') {
              thinkingSteps.push({
                step: event.step as number || thinkingSteps.length + 1,
                agent: stepAgent,
                content: '',
                toolName: stepToolName,
                toolArgs: event.tool_args as Record<string, unknown> | undefined,
              });
            } else if (stepToolName === 'delegate') {
              thinkingSteps.push({
                step: event.step as number || thinkingSteps.length + 1,
                agent: stepAgent,
                content: '',
                toolName: 'delegate',
                toolArgs: event.tool_args as Record<string, unknown> | undefined,
              });
            }

            if (stepObservation) {
              const lastIdx = thinkingSteps.length - 1;
              if (lastIdx >= 0 && thinkingSteps[lastIdx].toolName) {
                thinkingSteps[lastIdx].observation = stepObservation;
              } else {
                thinkingSteps.push({
                  step: event.step as number || thinkingSteps.length + 1,
                  agent: stepAgent,
                  content: '',
                  observation: stepObservation,
                });
              }
            }

            if (!stepToolName && !stepObservation && event.content) {
              thinkingSteps.push({
                step: event.step as number || thinkingSteps.length + 1,
                agent: stepAgent,
                content: event.content as string,
              });
            }

            setMessages(prev =>
              prev.map(m =>
                m.id === assistantId ? { ...m, thinkingSteps: [...thinkingSteps] } : m,
              ),
            );
          } else if (type === 'handoff') {
            thinkingSteps.push({
              step: thinkingSteps.length + 1,
              agent: (event.from as string) || 'supervisor',
              content: (event.content as string) || `委派给 ${getAgentLabel((event.to as string) || '')}`,
              isHandoff: true,
              handoffTo: event.to as string,
              handoffTask: (event.task as string) || (event.content as string) || undefined,
            });
            setMessages(prev =>
              prev.map(m =>
                m.id === assistantId ? { ...m, thinkingSteps: [...thinkingSteps] } : m,
              ),
            );
          } else if (type === 'answer_start') {
            // answer 即将开始流式输出
          } else if (type === 'done') {
            setMessages(prev =>
              prev.map(m =>
                m.id === assistantId
                  ? { ...m, content: fullContent, steps: event.steps as number, agentName, durationMs: event.duration_ms as number }
                  : m,
              ),
            );
          } else if (type === 'error') {
            fullContent = fullContent || `错误: ${event.error || '未知错误'}`;
            setMessages(prev =>
              prev.map(m =>
                m.id === assistantId ? { ...m, content: fullContent } : m,
              ),
            );
          } else if (type === 'heartbeat') {
            // heartbeat to keep connection alive, no UI update needed
          }
        },
        () => {
          setMessages(prev =>
            prev.map(m =>
              m.id === assistantId ? { ...m, content: fullContent } : m,
            ),
          );
          setLoading(false);
          loadSessions();
        },
        (err) => {
          setMessages(prev =>
            prev.map(m =>
              m.id === assistantId
                ? { ...m, content: fullContent || `流式响应中断: ${err.message}` }
                : m,
            ),
          );
          setLoading(false);
        },
      );
    } catch (err) {
      setMessages(prev =>
        prev.map(m =>
          m.id === assistantId
            ? { ...m, content: `网络错误: ${(err as Error).message}` }
            : m,
        ),
      );
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const sessionGroups = groupSessionsByTime(sessions);

  return (
    <div className="flex h-[calc(100vh-0px)] -m-6 lg:-m-8">
      {/* Conversation Sidebar */}
      <div className={`shrink-0 flex flex-col border-r border-white/5 bg-surface-950/80 transition-all duration-300 ${sidebarOpen ? 'w-64' : 'w-0 overflow-hidden'}`}>
        <div className="flex items-center justify-between px-3 h-12 border-b border-white/5">
          <button
            onClick={handleNewChat}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-cfa-500/15 text-cfa-300 text-xs font-medium hover:bg-cfa-500/25 transition-all border border-cfa-500/20"
          >
            <Plus className="w-3.5 h-3.5" />
            新对话
          </button>
          <button
            onClick={() => setSidebarOpen(false)}
            className="p-1 rounded text-zinc-500 hover:text-zinc-300 hover:bg-white/5 transition-colors"
          >
            <PanelLeftClose className="w-4 h-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto custom-scrollbar px-2 py-2">
          {sessionGroups.map(group => (
            <div key={group.label} className="mb-3">
              <p className="px-2 py-1 text-[10px] font-medium text-zinc-600 uppercase tracking-wider">{group.label}</p>
              {group.items.map(s => (
                <button
                  key={s.id}
                  onClick={() => handleSelectSession(s.id)}
                  className={`w-full text-left px-2.5 py-1.5 rounded-lg text-xs transition-all flex items-center gap-2 group ${
                    s.id === sessionId
                      ? 'bg-cfa-500/15 text-cfa-300'
                      : 'text-zinc-400 hover:text-zinc-200 hover:bg-white/5'
                  }`}
                >
                  <MessageSquare className="w-3 h-3 shrink-0 opacity-50" />
                  <span className="truncate flex-1">
                    {s.summary || '新对话'}
                  </span>
                </button>
              ))}
            </div>
          ))}
          {sessions.length === 0 && (
            <p className="text-xs text-zinc-600 px-3 py-6 text-center">暂无历史对话</p>
          )}
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top Bar */}
        <div className="flex items-center gap-3 px-4 h-12 border-b border-white/5 shrink-0">
          {!sidebarOpen && (
            <button
              onClick={() => setSidebarOpen(true)}
              className="p-1.5 rounded-lg text-zinc-500 hover:text-zinc-300 hover:bg-white/5 transition-colors"
            >
              <PanelLeft className="w-4 h-4" />
            </button>
          )}
          <div className="flex items-center gap-2">
            <div className="w-5 h-5 rounded-md bg-gradient-to-br from-cfa-500 to-cfa-700 flex items-center justify-center">
              <Sparkles className="w-3 h-3 text-white" />
            </div>
            <span className="text-sm font-medium text-zinc-300">AI 对话</span>
          </div>
          <div className="flex-1" />
          {!agentPanelOpen && (
            <button
              onClick={() => setAgentPanelOpen(true)}
              className="p-1.5 rounded-lg text-zinc-500 hover:text-zinc-300 hover:bg-white/5 transition-colors relative"
              title="显示智能体状态"
            >
              <PanelLeft className="w-4 h-4 rotate-180" />
              {loading && activeThinkingSteps.length > 0 && (
                <span className="absolute -top-0.5 -right-0.5 w-2 h-2 bg-cfa-400 rounded-full animate-pulse" />
              )}
            </button>
          )}
        </div>

        {/* Messages Area */}
        <div className="flex-1 overflow-y-auto custom-scrollbar">
          {!hasMessages ? (
            <div className="flex flex-col items-center justify-center h-full px-4">
              <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-cfa-500/20 to-cfa-700/20 flex items-center justify-center mb-6 glow-sm">
                <Sparkles className="w-8 h-8 text-cfa-400" />
              </div>
              <h2 className="text-2xl font-semibold text-white mb-2">有什么可以帮你的？</h2>
              <div className="grid grid-cols-2 gap-3 w-full max-w-lg mt-8">
                {SUGGESTIONS.map((s, i) => (
                  <button
                    key={i}
                    onClick={() => handleSend(s.label)}
                    className="flex items-center gap-3 px-4 py-3 rounded-xl border border-white/5 bg-white/[0.02] hover:bg-white/[0.06] hover:border-cfa-500/20 text-left transition-all group"
                  >
                    <span className="text-lg shrink-0">{s.icon}</span>
                    <span className="text-sm text-zinc-400 group-hover:text-zinc-200 transition-colors line-clamp-2">{s.label}</span>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="max-w-3xl mx-auto px-4 py-6 space-y-6">
              {messages.map((msg) => (
                <div key={msg.id} className={`flex gap-4 animate-in ${msg.role === 'user' ? 'justify-end' : ''}`}>
                  {msg.role !== 'user' && (
                    <div className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 mt-0.5 ${
                      msg.role === 'system' ? 'bg-amber-500/20' : 'bg-gradient-to-br from-cfa-500/30 to-cfa-700/30'
                    }`}>
                      {msg.role === 'system' ? (
                        <Loader2 className="w-3.5 h-3.5 text-amber-400" />
                      ) : (
                        <Bot className="w-3.5 h-3.5 text-cfa-300" />
                      )}
                    </div>
                  )}

                  <div className={`${
                    msg.role === 'user'
                      ? 'bg-cfa-500/15 text-zinc-100 rounded-2xl rounded-br-md px-4 py-2.5 max-w-[80%]'
                      : 'flex-1 min-w-0'
                  }`}>
                    {/* Thinking Steps - collapsible */}
                    {msg.role === 'assistant' && (msg.thinkingSteps.length > 0 || (loading && msg.id === streamIdRef.current)) && (
                      <ThinkingSection
                        steps={msg.thinkingSteps}
                        loading={loading && msg.id === streamIdRef.current && !msg.content}
                      />
                    )}

                    {/* Message Content */}
                    {loading && msg.id === streamIdRef.current && !msg.content ? (
                      <div className="space-y-2">
                        <div className="flex items-center gap-2 text-zinc-500 py-1">
                          <div className="flex gap-1">
                            <span className="w-1.5 h-1.5 bg-cfa-400/60 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                            <span className="w-1.5 h-1.5 bg-cfa-400/60 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                            <span className="w-1.5 h-1.5 bg-cfa-400/60 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                          </div>
                          <span className="text-xs">思考中</span>
                        </div>
                        {msg.thinkingSteps.length > 0 && (
                          <div className="text-xs text-zinc-500 leading-relaxed animate-pulse">
                            {msg.thinkingSteps[msg.thinkingSteps.length - 1]?.content?.slice(0, 120)}
                            {msg.thinkingSteps[msg.thinkingSteps.length - 1]?.content?.length > 120 ? '...' : ''}
                          </div>
                        )}
                      </div>
                    ) : msg.content ? (
                      <div className="text-sm whitespace-pre-wrap leading-relaxed text-zinc-200">
                        {msg.content}
                        {loading && msg.id === streamIdRef.current && msg.content && (
                          <span className="inline-block w-1.5 h-4 bg-cfa-400 animate-pulse ml-0.5 align-middle" />
                        )}
                      </div>
                    ) : null}

                    {/* Meta Info */}
                    {msg.role === 'assistant' && msg.content && (
                      <div className="flex items-center gap-2 mt-1.5">
                        <span className="text-[10px] text-zinc-600">
                          {new Date(msg.timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
                        </span>
                        {msg.agentName && (
                          <span className="text-[10px] text-zinc-600">
                            · {msg.agentName}
                            {msg.steps != null ? ` · ${msg.steps} steps` : ''}
                            {msg.durationMs != null ? ` · ${(msg.durationMs / 1000).toFixed(1)}s` : ''}
                          </span>
                        )}
                      </div>
                    )}
                  </div>

                  {msg.role === 'user' && (
                    <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-blue-500/30 to-cyan-600/30 flex items-center justify-center shrink-0 mt-0.5">
                      <User className="w-3.5 h-3.5 text-blue-300" />
                    </div>
                  )}
                </div>
              ))}

              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Input Bar */}
        <div className="shrink-0 px-4 pb-4 pt-2">
          <div className="max-w-3xl mx-auto">
            <div className="flex items-center gap-2 bg-surface-900/80 border border-white/5 rounded-2xl px-4 py-2 focus-within:border-cfa-500/30 focus-within:bg-surface-900 transition-all">
              <input
                ref={inputRef}
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="输入你的问题或任务..."
                disabled={loading}
                className="flex-1 bg-transparent border-none text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none py-1.5"
              />
              <button
                onClick={() => handleSend()}
                disabled={loading || !input.trim()}
                className="p-2 rounded-xl bg-cfa-500 text-white hover:bg-cfa-400 disabled:opacity-20 disabled:cursor-not-allowed transition-all shrink-0"
              >
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
              </button>
            </div>
            <p className="text-[10px] text-zinc-700 text-center mt-2">AI 可能产生不准确的内容，请注意甄别</p>
          </div>
        </div>
      </div>

      {/* Agent Status Panel */}
      {agentPanelOpen ? (
        <AgentStatusPanel
          steps={activeThinkingSteps}
          loading={loading}
          open={agentPanelOpen}
          onToggle={() => setAgentPanelOpen(false)}
        />
      ) : null}
    </div>
  );
}