import { Bot, Wrench, Activity, Sparkles, ArrowUpRight, Circle, Eye, Cpu, Code, Search, Database, Clock } from 'lucide-react';
import { useApi } from '../hooks/useApi';
import { api, type AppInfo, type HealthCheck } from '../lib/api';

const AGENT_META: Record<string, { icon: React.ElementType; gradient: string; color: string; desc: string }> = {
  supervisor: {
    icon: Eye,
    gradient: 'from-cfa-500 to-purple-600',
    color: 'text-purple-400',
    desc: '中央调度，分析任务并委派给专家智能体',
  },
  executor: {
    icon: Cpu,
    gradient: 'from-blue-500 to-cyan-600',
    color: 'text-blue-400',
    desc: '信息获取与执行，搜索/抓取/编码/查询',
  },
  code_agent: {
    icon: Code,
    gradient: 'from-teal-500 to-emerald-600',
    color: 'text-teal-400',
    desc: '编码专家，写代码→报错→修复→重跑闭环',
  },
};

function getAgentMeta(id: string) {
  return AGENT_META[id] || {
    icon: Bot,
    gradient: 'from-zinc-500 to-zinc-600',
    color: 'text-zinc-400',
    desc: '智能体',
  };
}

function StatCard({
  icon: Icon,
  label,
  value,
  sub,
  gradient,
  delay,
}: {
  icon: React.ElementType;
  label: string;
  value: string | number;
  sub?: string;
  gradient: string;
  delay: number;
}) {
  return (
    <div
      className="glass-card rounded-2xl p-5 animate-in hover:scale-[1.02] transition-transform duration-300"
      style={{ animationDelay: `${delay}ms` }}
    >
      <div className="flex items-start justify-between">
        <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${gradient} flex items-center justify-center glow-sm`}>
          <Icon className="w-5 h-5 text-white" />
        </div>
        <ArrowUpRight className="w-4 h-4 text-zinc-600" />
      </div>
      <div className="mt-4">
        <p className="text-2xl font-bold text-white">{value}</p>
        <p className="text-sm text-zinc-400 mt-1">{label}</p>
        {sub && <p className="text-xs text-zinc-500 mt-0.5">{sub}</p>}
      </div>
    </div>
  );
}

export default function Dashboard() {
  const health = useApi(() => api.health());
  const appInfo = useApi(() => api.appInfo());
  const agents = useApi(() => api.agents.list());
  const tools = useApi(() => api.tools.list());

  const agentList = agents.data?.data?.agents || [];
  const agentCount = agents.data?.data?.total ?? '-';
  const toolCount = Array.isArray(tools.data?.data) ? tools.data.data.length : '-';
  const status = health.data?.status ?? '...';

  return (
    <div className="space-y-8 animate-in">
      <div>
        <h1 className="text-3xl font-bold text-white tracking-tight">
          <span className="gradient-text">CFA Agent</span> 仪表盘
        </h1>
        <p className="text-zinc-400 mt-2 text-sm">
          {appInfo.data?.description || '自主决策智能体集群系统'}
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={Activity}
          label="系统状态"
          value={status === 'healthy' ? '运行中' : status}
          sub={appInfo.data?.version ? `v${appInfo.data.version}` : undefined}
          gradient="from-emerald-500 to-teal-600"
          delay={0}
        />
        <StatCard
          icon={Bot}
          label="智能体"
          value={agentCount}
          sub="协作集群"
          gradient="from-cfa-500 to-purple-600"
          delay={100}
        />
        <StatCard
          icon={Wrench}
          label="工具"
          value={toolCount}
          sub="可用"
          gradient="from-amber-500 to-orange-600"
          delay={200}
        />
        <StatCard
          icon={Clock}
          label="运行时间"
          value={health.data?.timestamp ? formatUptime(health.data.timestamp) : '-'}
          sub="自上次检查"
          gradient="from-rose-500 to-pink-600"
          delay={300}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <AgentCluster agents={agentList} />
        </div>
        <div className="space-y-6">
          <QuickActions />
          <SystemInfo appInfo={appInfo.data} health={health.data} />
        </div>
      </div>
    </div>
  );
}

function AgentCluster({ agents }: { agents: { id: string; name: string; role: string; status: string; config: Record<string, unknown> | null }[] }) {
  return (
    <div className="glass-card rounded-2xl p-6">
      <h2 className="text-lg font-semibold text-white flex items-center gap-2 mb-5">
        <Sparkles className="w-5 h-5 text-cfa-400" />
        智能体集群
      </h2>
      <div className="space-y-3">
        {agents.map((agent) => {
          const meta = getAgentMeta(agent.id);
          const MetaIcon = meta.icon;
          const tools = (agent.config as Record<string, string[]>)?.tools || [];
          const isEntryPoint = agent.role === 'supervisor' || agent.id === 'supervisor';

          return (
            <div
              key={agent.id}
              className="flex items-start gap-4 p-4 rounded-xl bg-white/[0.02] border border-white/5 hover:border-cfa-500/20 hover:bg-white/[0.04] transition-all group"
            >
              <div className={`w-11 h-11 rounded-xl bg-gradient-to-br ${meta.gradient} flex items-center justify-center shrink-0`}>
                <MetaIcon className="w-5 h-5 text-white" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <h3 className="text-white font-semibold text-sm">{agent.name}</h3>
                  {isEntryPoint && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-cfa-500/15 text-cfa-400 border border-cfa-500/20">
                      入口
                    </span>
                  )}
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                    agent.status === 'running' || agent.status === 'busy'
                      ? 'bg-emerald-500/15 text-emerald-400'
                      : 'bg-zinc-500/15 text-zinc-400'
                  }`}>
                    {agent.status === 'running' || agent.status === 'busy' ? '活跃' : '空闲'}
                  </span>
                </div>
                <p className="text-xs text-zinc-500 mt-0.5">{meta.desc}</p>
                {tools.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-2">
                    {tools.map((t: string) => {
                      const toolIcon = getToolIcon(t);
                      return (
                        <span key={t} className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-zinc-400">
                          {toolIcon}
                          {t}
                        </span>
                      );
                    })}
                  </div>
                )}
              </div>
              <ArrowUpRight className="w-4 h-4 text-zinc-700 group-hover:text-cfa-400 transition-colors shrink-0 mt-1" />
            </div>
          );
        })}

        {agents.length === 0 && (
          <div className="text-center py-8">
            <Bot className="w-10 h-10 text-zinc-700 mx-auto mb-3" />
            <p className="text-sm text-zinc-500">加载智能体信息...</p>
          </div>
        )}
      </div>
    </div>
  );
}

function getToolIcon(toolName: string) {
  if (toolName.includes('search') || toolName.includes('web_search')) return <Search className="w-2.5 h-2.5" />;
  if (toolName.includes('code') || toolName.includes('executor')) return <Code className="w-2.5 h-2.5" />;
  if (toolName.includes('db') || toolName.includes('query')) return <Database className="w-2.5 h-2.5" />;
  return <Circle className="w-2 h-2 fill-current" />;
}

function QuickActions() {
  return (
    <div className="glass-card rounded-2xl p-6">
      <h2 className="text-lg font-semibold text-white flex items-center gap-2">
        <Sparkles className="w-5 h-5 text-cfa-400" />
        快速操作
      </h2>
      <div className="mt-4 space-y-2">
        {[
          { label: '发起对话', desc: '与 AI 对话或智能调度完成任务', path: '/chat' },
          { label: '查看工具集', desc: '浏览可用的工具和技能', path: '/tools' },
        ].map((action, i) => (
          <a
            key={i}
            href={action.path}
            className="flex items-center gap-3 p-3 rounded-xl glass-hover transition-all duration-200 group cursor-pointer"
          >
            <div className="w-8 h-8 rounded-lg bg-white/5 flex items-center justify-center group-hover:bg-cfa-500/20 transition-colors">
              <Circle className="w-3 h-3 text-cfa-400 fill-cfa-400" />
            </div>
            <div>
              <p className="text-sm font-medium text-zinc-200">{action.label}</p>
              <p className="text-xs text-zinc-500">{action.desc}</p>
            </div>
            <ArrowUpRight className="w-4 h-4 text-zinc-600 ml-auto group-hover:text-cfa-400 transition-colors" />
          </a>
        ))}
      </div>
    </div>
  );
}

function SystemInfo({ appInfo, health }: { appInfo: AppInfo | null; health: HealthCheck | null }) {
  return (
    <div className="glass-card rounded-2xl p-6">
      <h2 className="text-lg font-semibold text-white flex items-center gap-2">
        <Activity className="w-5 h-5 text-emerald-400" />
        系统信息
      </h2>
      <div className="mt-4 space-y-3">
        {[
          { label: '应用名称', value: appInfo?.name || 'CFA-Agent' },
          { label: '版本', value: appInfo?.version || '-' },
          { label: 'API 状态', value: health?.status || '-' },
          { label: '检查时间', value: health?.timestamp ? new Date(health.timestamp).toLocaleString('zh-CN') : '-' },
        ].map((info, i) => (
          <div key={i} className="flex items-center justify-between py-2 border-b border-white/5 last:border-0">
            <span className="text-sm text-zinc-400">{info.label}</span>
            <span className="text-sm text-zinc-200 font-mono">{info.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function formatUptime(timestamp: string) {
  try {
    const diff = Date.now() - new Date(timestamp).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 60) return `${mins}m`;
    const hours = Math.floor(mins / 60);
    return `${hours}h ${mins % 60}m`;
  } catch {
    return '-';
  }
}