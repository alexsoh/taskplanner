import { useEffect, useState } from 'react';
import * as api from './api/client.ts';
import HistoryPage from './pages/HistoryPage.tsx';
import ProfilesPage from './pages/ProfilesPage.tsx';
import SchedulePage from './pages/SchedulePage.tsx';
import SettingsPage from './pages/SettingsPage.tsx';
import type { Profile } from './types.ts';

type Tab = 'profiles' | 'schedule' | 'history' | 'settings';

export default function App() {
  const [tab, setTab] = useState<Tab>('profiles');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [profiles, setProfiles] = useState<Profile[]>([]);

  useEffect(() => {
    api.listProfiles().then((list) => {
      setProfiles(list);
      setSelectedId((cur) => cur ?? (list[0]?.id ?? null));
    });
  }, []);

  const selected = profiles.find((p) => p.id === selectedId) ?? null;

  const tabs: { id: Tab; label: string }[] = [
    { id: 'profiles', label: 'Profiles' },
    { id: 'schedule', label: 'Schedule' },
    { id: 'history', label: 'History' },
    { id: 'settings', label: 'Settings' },
  ];

  return (
    <div className="min-h-screen bg-bg-primary text-text-primary">
      <header className="border-b border-border bg-bg-secondary px-4 py-3 flex items-center gap-4">
        <h1 className="text-xl font-bold text-accent">TaskPlanner</h1>
        <nav className="flex gap-1">
          {tabs.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`px-3 py-1.5 rounded text-sm ${
                tab === t.id ? 'bg-accent text-bg-primary' : 'text-text-secondary hover:bg-bg-tertiary'
              }`}
            >
              {t.label}
            </button>
          ))}
        </nav>
        {selected && tab === 'schedule' && (
          <span className="ml-auto text-sm text-text-muted flex items-center gap-2">
            <span className="w-2 h-2 rounded-full" style={{ background: selected.color }} />
            {selected.name}
          </span>
        )}
      </header>
      <main className="max-w-6xl mx-auto p-4">
        {tab === 'profiles' && (
          <ProfilesPage
            selectedId={selectedId}
            onSelect={(id) => {
              setSelectedId(id);
              if (id) setTab('schedule');
            }}
          />
        )}
        {tab === 'schedule' && <SchedulePage profile={selected} />}
        {tab === 'history' && <HistoryPage profiles={profiles} />}
        {tab === 'settings' && <SettingsPage />}
      </main>
    </div>
  );
}
