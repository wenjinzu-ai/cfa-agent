import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';

export default function Layout() {
  return (
    <div className="flex h-screen bg-surface-950 text-zinc-200 overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        <div className="relative min-h-full">
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-cfa-950/40 via-transparent to-transparent pointer-events-none" />
          <div className="relative z-10 p-6 lg:p-8">
            <Outlet />
          </div>
        </div>
      </main>
    </div>
  );
}