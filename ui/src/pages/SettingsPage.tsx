import { Settings, Server, Shield, Activity, Info } from 'lucide-react';
import { useApi } from '../hooks/useApi';
import { api } from '../lib/api';

export default function SettingsPage() {
  const mcp = useApi(() => api.mcp.servers());
  const health = useApi(() => api.health());
  const appInfo = useApi(() => api.appInfo());

  const mcpServers = Array.isArray(mcp.data?.data) ? mcp.data.data : [];

  const handleConnectMCP = async (name: string) => {
    try {
      await api.mcp.connect(name);
      mcp.refetch();
    } catch (err) {
      alert((err as Error).message);
    }
  };

  const handleDisconnectMCP = async (name: string) => {
    try {
      await api.mcp.disconnect(name);
      mcp.refetch();
    } catch (err) {
      alert((err as Error).message);
    }
  };

  return (
    <div className="space-y-8 animate-in">
      <div>
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <Settings className="w-6 h-6 text-cfa-400" />
          设置
        </h1>
        <p className="text-sm text-zinc-400 mt-1">系统配置和状态信息</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="glass-card rounded-2xl p-6">
          <h2 className="text-lg font-semibold text-white flex items-center gap-2 mb-4">
            <Activity className="w-5 h-5 text-emerald-400" />
            系统状态
          </h2>
          <div className="space-y-3">
            {[
              { label: '应用名称', value: appInfo.data?.name || 'CFA-Agent' },
              { label: '版本', value: appInfo.data?.version || '-' },
              { label: '状态', value: appInfo.data?.status || '-' },
              { label: '健康检查', value: health.data?.status || '-' },
              { label: '检查时间', value: health.data?.timestamp || '-' },
            ].map((info, i) => (
              <div key={i} className="flex justify-between py-2 border-b border-white/5 last:border-0">
                <span className="text-sm text-zinc-400">{info.label}</span>
                <span className="text-sm text-zinc-200">{info.value}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="glass-card rounded-2xl p-6">
          <h2 className="text-lg font-semibold text-white flex items-center gap-2 mb-4">
            <Server className="w-5 h-5 text-blue-400" />
            MCP 服务器
          </h2>
          {mcpServers.length === 0 ? (
            <div className="text-center py-8">
              <Server className="w-10 h-10 text-zinc-700 mx-auto mb-3" />
              <p className="text-zinc-500 text-sm">暂无 MCP 服务器</p>
            </div>
          ) : (
            <div className="space-y-2">
              {mcpServers.map((server: any) => (
                <div key={server.name} className="flex items-center justify-between p-3 rounded-xl bg-white/5">
                  <div>
                    <p className="text-sm text-zinc-200 font-medium">{server.name}</p>
                    <p className="text-xs text-zinc-500">{server.description || '无描述'}</p>
                  </div>
                  <button
                    onClick={() => server.connected ? handleDisconnectMCP(server.name) : handleConnectMCP(server.name)}
                    className={`text-xs px-3 py-1 rounded-lg transition-colors ${
                      server.connected
                        ? 'bg-red-500/10 text-red-400 hover:bg-red-500/20'
                        : 'bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20'
                    }`}
                  >
                    {server.connected ? '断开' : '连接'}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="glass-card rounded-2xl p-6">
          <h2 className="text-lg font-semibold text-white flex items-center gap-2 mb-4">
            <Shield className="w-5 h-5 text-purple-400" />
            安全防护
          </h2>
          <div className="space-y-3">
            {[
              { label: '输入守卫', value: '已启用', status: 'active' },
              { label: '输出守卫', value: '已启用', status: 'active' },
              { label: '行为守卫', value: '已启用', status: 'active' },
              { label: '工具守卫', value: '已启用', status: 'active' },
            ].map((guard, i) => (
              <div key={i} className="flex justify-between py-2 border-b border-white/5 last:border-0">
                <span className="text-sm text-zinc-400">{guard.label}</span>
                <span className={`text-xs px-2 py-0.5 rounded-full ${
                  guard.status === 'active' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-zinc-500/10 text-zinc-500'
                }`}>
                  {guard.value}
                </span>
              </div>
            ))}
          </div>
        </div>

        <div className="glass-card rounded-2xl p-6">
          <h2 className="text-lg font-semibold text-white flex items-center gap-2 mb-4">
            <Info className="w-5 h-5 text-amber-400" />
            关于
          </h2>
          <div className="space-y-4">
            <p className="text-sm text-zinc-400 leading-relaxed">
              CFA-Agent 是一个自主决策智能体集群系统，支持多智能体协作、任务规划、工具调用和持续学习。
            </p>
            <div className="flex gap-2">
              <span className="text-xs px-2 py-1 rounded-lg bg-cfa-500/10 text-cfa-400">React 19</span>
              <span className="text-xs px-2 py-1 rounded-lg bg-blue-500/10 text-blue-400">TypeScript</span>
              <span className="text-xs px-2 py-1 rounded-lg bg-emerald-500/10 text-emerald-400">TailwindCSS</span>
              <span className="text-xs px-2 py-1 rounded-lg bg-amber-500/10 text-amber-400">Vite 8</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}