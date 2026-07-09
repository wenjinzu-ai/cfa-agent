import { useState, useEffect } from 'react';
import {
  Bot,
  Wrench,
  ArrowRight,
  ChevronDown,
  ChevronRight,
  CheckCircle2,
  Loader2,
  Circle,
  PanelRightClose,
  PanelRight,
  Eye,
  Brain,
} from 'lucide-react';

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

type AgentStatus = 'idle' | 'thinking' | 'acting' | 'done';

type AgentInfo = {
  id: string;
  label: string;
  status: AgentStatus;
  steps: ThinkingStep[];
};

const AGENT_LABELS: Record<string, string> = {
  supervisor: '监督者',
  planner: '规划者',
  executor: '执行者',
  reviewer: '审查者',
  code_agent: '编码专家',
};

const AGENT_COLORS: Record<string, { bg: string; text: string; border: string; dot: string }> = {
  supervisor: { bg: 'bg-violet-500/10', text: 'text-violet-300', border: 'border-violet-500/20', dot: 'bg-violet-400' },
  planner:    { bg: 'bg-blue-500/10',   text: 'text-blue-300',   border: 'border-blue-500/20',   dot: 'bg-blue-400' },
  executor:   { bg: 'bg-emerald-500/10', text: 'text-emerald-300', border: 'border-emerald-500/20', dot: 'bg-emerald-400' },
  reviewer:   { bg: 'bg-amber-500/10',  text: 'text-amber-300',  border: 'border-amber-500/20',  dot: 'bg-amber-400' },
  code_agent: { bg: 'bg-cyan-500/10',   text: 'text-cyan-300',   border: 'border-cyan-500/20',   dot: 'bg-cyan-400' },
};

function getAgentLabel(id: string) {
  return AGENT_LABELS[id] || id;
}

function getAgentColor(id: string) {
  return AGENT_COLORS[id] || { bg: 'bg-zinc-500/10', text: 'text-zinc-300', border: 'border-zinc-500/20', dot: 'bg-zinc-400' };
}

function extractAgentGroups(steps: ThinkingStep[], isComplete: boolean): AgentInfo[] {
  const agentMap = new Map<string, ThinkingStep[]>();
  const agentOrder: string[] = [];

  for (const step of steps) {
    const agentId = step.agent || 'supervisor';
    if (!agentMap.has(agentId)) {
      agentMap.set(agentId, []);
      agentOrder.push(agentId);
    }
    agentMap.get(agentId)!.push(step);

    if (step.isHandoff && step.handoffTo && !agentMap.has(step.handoffTo)) {
      agentMap.set(step.handoffTo, []);
      agentOrder.push(step.handoffTo);
    }
  }

  const activeAgentId = agentOrder.length > 0 ? agentOrder[agentOrder.length - 1] : null;

  return agentOrder.map(id => {
    const agentSteps = agentMap.get(id) || [];
    const lastStep = agentSteps[agentSteps.length - 1];
    let status: AgentStatus = 'thinking';

    if (isComplete) {
      status = 'done';
    } else if (lastStep) {
      if (lastStep.isHandoff) {
        status = 'done';
      } else if (id !== activeAgentId) {
        status = 'done';
      } else if (lastStep.toolName) {
        status = lastStep.observation ? 'thinking' : 'acting';
      }
    }

    return { id, label: getAgentLabel(id), status, steps: agentSteps };
  });
}

function StatusDot({ status, color }: { status: AgentStatus; color: string }) {
  if (status === 'done') return <CheckCircle2 className="w-3.5 h-3.5 text-zinc-500" />;
  if (status === 'thinking') return <Loader2 className={`w-3.5 h-3.5 ${color} animate-spin`} />;
  if (status === 'acting') return <div className={`w-2 h-2 rounded-full ${color} animate-pulse`} />;
  return <Circle className="w-3.5 h-3.5 text-zinc-600" />;
}

function StatusLabel({ status }: { status: AgentStatus }) {
  const labels: Record<AgentStatus, string> = {
    idle: '等待中',
    thinking: '思考中',
    acting: '执行中',
    done: '已完成',
  };
  const colors: Record<AgentStatus, string> = {
    idle: 'text-zinc-600',
    thinking: 'text-zinc-400',
    acting: 'text-zinc-400',
    done: 'text-zinc-500',
  };
  return <span className={`text-[11px] ${colors[status]}`}>{labels[status]}</span>;
}

function AgentCard({ agent, isLast }: { agent: AgentInfo; isLast: boolean }) {
  const color = getAgentColor(agent.id);
  const isActive = agent.status === 'thinking' || agent.status === 'acting';
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (isActive) setExpanded(true);
  }, [isActive]);

  return (
    <div className="relative">
      <div
        className={`rounded-lg border ${color.border} ${color.bg} transition-all ${
          isActive ? 'ring-1 ring-inset ring-white/5' : ''
        }`}
      >
        <button
          onClick={() => setExpanded(!expanded)}
          className="w-full flex items-center gap-2.5 px-3 py-2.5 text-left hover:bg-white/[0.02] transition-colors"
        >
          <div className={`w-6 h-6 rounded-md ${color.bg} flex items-center justify-center shrink-0`}>
            <Bot className={`w-3.5 h-3.5 ${color.text}`} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className={`text-xs font-medium ${color.text}`}>{agent.label}</span>
              <StatusDot status={agent.status} color={color.dot} />
              <StatusLabel status={agent.status} />
            </div>
            {agent.steps.length > 0 && (
              <p className="text-[10px] text-zinc-600 mt-0.5 truncate">
                {agent.steps.length} 步
                {agent.steps.some(s => s.toolName) && ` · ${agent.steps.filter(s => s.toolName).map(s => s.toolName).join(', ')}`}
              </p>
            )}
          </div>
          {agent.steps.length > 0 && (
            expanded ? <ChevronDown className="w-3 h-3 text-zinc-600 shrink-0" /> : <ChevronRight className="w-3 h-3 text-zinc-600 shrink-0" />
          )}
        </button>

        {expanded && agent.steps.length > 0 && (
          <div className="px-3 pb-2.5 space-y-1.5 border-t border-white/5 pt-2">
            {agent.steps.map((step, i) => (
              <div key={i} className="text-[11px] leading-relaxed">
                {step.isHandoff ? (
                  <div className="flex items-center gap-1.5 text-cfa-400/80">
                    <ArrowRight className="w-3 h-3 shrink-0" />
                    <span>
                      委派给 <span className="text-cfa-300">{getAgentLabel(step.handoffTo || '')}</span>
                    </span>
                    {step.handoffTask && (
                      <span className="text-zinc-600 ml-1 truncate max-w-[140px]">
                        — {step.handoffTask.slice(0, 40)}
                      </span>
                    )}
                  </div>
                ) : step.toolName === 'delegate' ? (
                  <div className="flex items-center gap-1.5 text-cfa-400/80">
                    <ArrowRight className="w-3 h-3 shrink-0" />
                    <span className="text-zinc-500">{getAgentLabel(step.agent)}</span>
                    <span>
                      委派给 <span className="text-cfa-300">{getAgentLabel((step.toolArgs as Record<string, string>)?.role || '')}</span>
                    </span>
                    {(step.toolArgs as Record<string, string>)?.task && (
                      <span className="text-zinc-600 ml-1 truncate max-w-[140px]">
                        — {(step.toolArgs as Record<string, string>).task.slice(0, 40)}
                      </span>
                    )}
                  </div>
                ) : step.toolName ? (
                  <div className="flex items-start gap-1.5 text-zinc-400">
                    <Wrench className="w-3 h-3 text-cfa-500/60 shrink-0 mt-0.5" />
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className={`px-1.5 py-0.5 ${color.bg} rounded text-[10px] ${color.text}`}>
                          {step.toolName}
                        </span>
                        {step.toolArgs && Object.keys(step.toolArgs).length > 0 && (
                          <span className="text-zinc-600 truncate max-w-[120px]">
                            {JSON.stringify(step.toolArgs).slice(0, 50)}
                          </span>
                        )}
                      </div>
                      {step.observation && (
                        <p className="text-zinc-600 mt-0.5 line-clamp-2">{step.observation.slice(0, 120)}</p>
                      )}
                    </div>
                  </div>
                ) : step.observation ? (
                  <div className="flex items-start gap-1.5 text-zinc-500">
                    <Wrench className="w-3 h-3 text-zinc-600 shrink-0 mt-0.5" />
                    <span className="text-zinc-500">{getAgentLabel(step.agent)}</span>
                    <span className="text-zinc-600 line-clamp-2">{step.observation.slice(0, 120)}</span>
                  </div>
                ) : step.content ? (
                  <div className="flex items-start gap-1.5 text-zinc-500">
                    <Brain className="w-3 h-3 text-zinc-600 shrink-0 mt-0.5" />
                    <span className="line-clamp-2">{step.content.slice(0, 120)}</span>
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        )}
      </div>

      {!isLast && (
        <div className="flex justify-center py-1">
          <div className="w-px h-3 bg-white/5" />
        </div>
      )}
    </div>
  );
}

type AgentStatusPanelProps = {
  steps: ThinkingStep[];
  loading: boolean;
  open: boolean;
  onToggle: () => void;
};

export default function AgentStatusPanel({ steps, loading, open, onToggle }: AgentStatusPanelProps) {
  const agents = extractAgentGroups(steps, !loading);

  if (!open) {
    return (
      <button
        onClick={onToggle}
        className="fixed right-4 top-16 z-10 p-2 rounded-lg bg-surface-900/80 border border-white/5 text-zinc-500 hover:text-zinc-300 hover:bg-white/5 transition-all"
        title="显示智能体状态"
      >
        <PanelRight className="w-4 h-4" />
        {loading && agents.length > 0 && (
          <span className="absolute -top-1 -left-1 w-2 h-2 bg-cfa-400 rounded-full animate-pulse" />
        )}
      </button>
    );
  }

  return (
    <div className="shrink-0 w-80 flex flex-col border-l border-white/5 bg-surface-950/80">
      <div className="flex items-center justify-between px-3 h-12 border-b border-white/5 shrink-0">
        <div className="flex items-center gap-2">
          <Eye className="w-3.5 h-3.5 text-cfa-400/60" />
          <span className="text-xs font-medium text-zinc-400">智能体状态</span>
          {loading && (
            <span className="flex gap-0.5">
              <span className="w-1 h-1 bg-cfa-400/60 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
              <span className="w-1 h-1 bg-cfa-400/60 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
              <span className="w-1 h-1 bg-cfa-400/60 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
            </span>
          )}
        </div>
        <button
          onClick={onToggle}
          className="p-1 rounded text-zinc-500 hover:text-zinc-300 hover:bg-white/5 transition-colors"
        >
          <PanelRightClose className="w-4 h-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-3">
        {agents.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-zinc-600">
            <Bot className="w-8 h-8 mb-3 opacity-30" />
            <p className="text-xs">
              {loading ? '等待智能体启动...' : '发送消息后查看智能体协作过程'}
            </p>
          </div>
        ) : (
          <div>
            {agents.map((agent, i) => (
              <AgentCard key={agent.id} agent={agent} isLast={i === agents.length - 1} />
            ))}
          </div>
        )}
      </div>

      {agents.length > 0 && (
        <div className="px-3 py-2 border-t border-white/5 shrink-0">
          <div className="flex items-center justify-between text-[10px] text-zinc-600">
            <span>{agents.length} 个智能体参与</span>
            <span>{steps.length} 个步骤</span>
          </div>
        </div>
      )}
    </div>
  );
}