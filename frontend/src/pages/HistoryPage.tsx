import { useEffect, useState } from 'react';
import * as api from '../api/client.ts';
import type { ExecutionRun, Profile } from '../types.ts';
import { CHANNEL_COLORS, channelLabel } from '../utils/notifications.ts';

type Props = {
  profiles: Profile[];
  selectedId: string | null;
  onSelectProfile: (id: string | null) => void;
};

function statusClass(status: string): string {
  if (status === 'success') return 'text-success';
  if (status === 'running') return 'text-text-secondary';
  return 'text-error';
}

export default function HistoryPage({ profiles, selectedId, onSelectProfile }: Props) {
  const [runs, setRuns] = useState<ExecutionRun[]>([]);
  const [profileFilter, setProfileFilter] = useState(selectedId ?? '');
  const [serverTimezone, setServerTimezone] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    setProfileFilter(selectedId ?? '');
  }, [selectedId]);

  useEffect(() => {
    api.getHealth().then((h) => {
      if (h.server_timezone) setServerTimezone(h.server_timezone);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    const params: { profile_id?: string; limit?: number } = { limit: 200 };
    if (profileFilter) params.profile_id = profileFilter;
    api.listExecutions(params).then(setRuns).catch((e) => setError(String(e)));
  }, [profileFilter]);

  const profileName = (id: string | null) => profiles.find((p) => p.id === id)?.name ?? id ?? '—';

  const handleFilterChange = (newFilter: string) => {
    setProfileFilter(newFilter);
    onSelectProfile(newFilter || null);
  };

  return (
    <div className="space-y-6">
      <div className="space-y-3">
        <h2 className="text-2xl font-bold text-text-primary">Execution History</h2>
        {serverTimezone && (
          <p className="text-xs text-text-muted">
            Times shown in server timezone ({serverTimezone})
          </p>
        )}
        <div className="flex items-center gap-2">
          <label className="text-sm font-medium text-text-secondary">Profile:</label>
          <select
            className="px-3 py-1.5 bg-bg-tertiary border border-border rounded text-sm"
            value={profileFilter}
            onChange={(e) => handleFilterChange(e.target.value)}
          >
            <option value="">All profiles</option>
            {profiles.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      {error && <p className="text-sm text-error">{error}</p>}
      {runs.length === 0 ? (
        <p className="text-sm text-text-muted">No executions yet.</p>
      ) : (
        <ul className="space-y-2">
          {runs.map((r) => (
            <li
              key={r.id}
              className="p-3 rounded-lg border border-border bg-bg-secondary text-sm flex flex-wrap gap-x-4 gap-y-1"
            >
              <span className={`font-medium ${statusClass(r.status)}`}>
                {r.status}
              </span>
              <span className="text-text-muted" title="Scheduled for">
                sched {r.scheduled_for_local || r.scheduled_for}
              </span>
              <span className="text-text-muted" title="Fired at">
                fired {r.fired_at_local || r.fired_at}
              </span>
              <span>{profileName(r.profile_id)}</span>
              <span style={{ color: CHANNEL_COLORS[r.channel] ?? undefined }}>{channelLabel(r.channel)}</span>
              <span className="flex-1 min-w-0 truncate">{r.label}</span>
              {r.error && <span className="w-full text-error text-xs">{r.error}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
