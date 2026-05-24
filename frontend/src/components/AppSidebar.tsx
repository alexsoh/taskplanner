import { useEffect, useState } from 'react';
import * as api from '../api/client.ts';

type Tab = 'profiles' | 'schedules' | 'history' | 'settings';

interface Props {
  tab: Tab;
  onTabChange: (tab: Tab) => void;
}

const NAV_ITEMS: { id: Tab; label: string; icon: string }[] = [
  { id: 'profiles', label: 'Profiles', icon: '👤' },
  { id: 'schedules', label: 'Schedules', icon: '📅' },
  { id: 'history', label: 'History', icon: '📜' },
  { id: 'settings', label: 'Settings', icon: '⚙️' },
];

export default function AppSidebar({ tab, onTabChange }: Props) {
  const [appVersion, setAppVersion] = useState<string | null>(null);

  useEffect(() => {
    const refreshVersion = () => {
      api.getVersion().then((r) => setAppVersion(r.version)).catch(() => {});
    };
    refreshVersion();
    window.addEventListener('taskplanner:version-updated', refreshVersion);
    return () => window.removeEventListener('taskplanner:version-updated', refreshVersion);
  }, []);

  return (
    <nav className="taskplanner-sidebar w-52 bg-bg-secondary border-r border-border flex flex-col shrink-0 pt-[env(safe-area-inset-top,0px)]">
      <div className="nav-header px-3 py-4 border-b border-border flex items-center gap-2">
        <span className="nav-logo-text text-base font-bold tracking-tight flex-1">TaskPlanner</span>
      </div>
      <div className="flex-1 py-2">
        {NAV_ITEMS.map((item) => (
          <button
            key={item.id}
            onClick={() => onTabChange(item.id)}
            className={`w-full text-left px-4 py-2.5 text-sm flex items-center gap-2.5 transition-colors ${
              tab === item.id
                ? 'bg-accent/15 text-accent border-r-2 border-accent'
                : 'text-text-secondary hover:bg-bg-hover hover:text-text-primary'
            }`}
          >
            <span className="nav-icon text-base">{item.icon}</span>
            <span className="nav-label">{item.label}</span>
          </button>
        ))}
      </div>
      {appVersion && (
        <div className="nav-version border-t border-border px-4 py-2.5 flex items-center justify-start">
          <span
            title="TaskPlanner version"
            className="text-xs text-text-muted font-mono no-underline"
          >
            v{appVersion}
          </span>
        </div>
      )}
    </nav>
  );
}
