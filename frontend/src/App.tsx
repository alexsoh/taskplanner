import { useCallback, useEffect, useState } from 'react';
import * as api from './api/client.ts';
import AppSidebar from './components/AppSidebar.tsx';
import HistoryPage from './pages/HistoryPage.tsx';
import ProfilesPage from './pages/ProfilesPage.tsx';
import SchedulePage from './pages/SchedulePage.tsx';
import SettingsPage from './pages/SettingsPage.tsx';
import type { Profile } from './types.ts';

type Tab = 'profiles' | 'schedules' | 'history' | 'settings';

export default function App() {
  const [tab, setTab] = useState<Tab>('profiles');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [profiles, setProfiles] = useState<Profile[]>([]);

  const loadProfiles = useCallback(async () => {
    try {
      const list = await api.listProfiles();
      setProfiles(list);
      setSelectedId((cur) => cur ?? (list[0]?.id ?? null));
    } catch (e) {
      console.error('Failed to load profiles:', e);
    }
  }, []);

  useEffect(() => {
    loadProfiles();
  }, [loadProfiles]);

  const handleSelectProfile = (id: string | null) => {
    setSelectedId(id);
    if (id) setTab('schedules');
  };

  const handleOpenHistory = (profileId: string | null) => {
    setSelectedId(profileId);
    setTab('history');
  };

  return (
    <div className="flex h-[100dvh] min-h-0 max-h-[100dvh] bg-bg-primary text-text-primary overflow-hidden">
      <AppSidebar tab={tab} onTabChange={setTab} />

      <div className="flex-1 flex flex-col overflow-hidden min-h-0 min-w-0">
        <main className="taskplanner-main flex-1 overflow-auto">
          {tab === 'profiles' && (
            <ProfilesPage
              profiles={profiles}
              selectedId={selectedId}
              onProfilesChange={loadProfiles}
              onSelectAndOpenSchedule={handleSelectProfile}
            />
          )}
          {tab === 'schedules' && (
            <SchedulePage
              profiles={profiles}
              selectedId={selectedId}
              onSelectProfile={setSelectedId}
              onOpenHistory={handleOpenHistory}
            />
          )}
          {tab === 'history' && (
            <HistoryPage
              profiles={profiles}
              selectedId={selectedId}
              onSelectProfile={setSelectedId}
            />
          )}
          {tab === 'settings' && <SettingsPage />}
        </main>
      </div>
    </div>
  );
}
