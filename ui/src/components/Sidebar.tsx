import { NavLink, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  MessageSquare,
  Wrench,
  Settings,
  Zap,
  PanelLeftClose,
  PanelLeft,
  ChevronRight,
} from 'lucide-react';
import { useState, useEffect } from 'react';

const navItems = [
  { to: '/', icon: LayoutDashboard, label: '仪表盘' },
  { to: '/chat', icon: MessageSquare, label: 'AI 对话' },
  { to: '/tools', icon: Wrench, label: '工具 & 技能' },
  { to: '/settings', icon: Settings, label: '设置' },
];

export default function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const location = useLocation();

  useEffect(() => {
    const handleResize = () => setCollapsed(window.innerWidth < 1024);
    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  return (
    <aside
      className={`glass flex flex-col border-r border-white/5 transition-all duration-300 ${
        collapsed ? 'w-16' : 'w-60'
      }`}
    >
      <div className="flex items-center gap-3 px-4 h-16 border-b border-white/5">
        <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-gradient-to-br from-cfa-500 to-cfa-700 glow-sm shrink-0">
          <Zap className="w-4 h-4 text-white" />
        </div>
        {!collapsed && (
          <span className="font-bold text-white tracking-tight text-sm">
            CFA Agent
          </span>
        )}
      </div>

      <nav className="flex-1 py-4 px-2 space-y-1 overflow-y-auto">
        {navItems.map(({ to, icon: Icon, label }) => {
          const isActive = location.pathname === to
            || (to !== '/' && location.pathname.startsWith(to));
          return (
            <NavLink
              key={to}
              to={to}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition-all duration-200 group ${
                isActive
                  ? 'bg-cfa-500/15 text-cfa-300 border border-cfa-500/20'
                  : 'text-zinc-400 hover:text-zinc-200 hover:bg-white/5'
              }`}
              title={collapsed ? label : undefined}
            >
              <Icon className={`w-5 h-5 shrink-0 ${isActive ? 'text-cfa-400' : 'text-zinc-500 group-hover:text-zinc-300'}`} />
              {!collapsed && <span>{label}</span>}
              {!collapsed && isActive && (
                <ChevronRight className="w-4 h-4 ml-auto text-cfa-400" />
              )}
            </NavLink>
          );
        })}
      </nav>

      <div className="p-2 border-t border-white/5">
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="flex items-center justify-center w-full p-2 rounded-lg text-zinc-500 hover:text-zinc-300 hover:bg-white/5 transition-colors"
        >
          {collapsed ? <PanelLeft className="w-4 h-4" /> : <PanelLeftClose className="w-4 h-4" />}
        </button>
      </div>
    </aside>
  );
}