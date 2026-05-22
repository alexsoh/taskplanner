import { useEffect, useState } from 'react';
import * as api from '../api/client.ts';
import type { ExecutionRun, Profile } from '../types.ts';
import { CHANNEL_COLORS } from '../utils/notifications.ts';

type Props = { profiles: Profile[] };

export default function HistoryPage({ profiles }: Props) {
  const [runs, setRuns] = useState<ExecutionRun[]>([]);
  const [profileFilter, setProfileFilter] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    const params: { profile_id?: string; limit?: number } = { limit: 200 };
    if (profileFilter) params.profile_id = profileFilter;
    api.listExecutions(params).then(setRuns).catch((e) => setError(String(e)));
  }, [profileFilter]);

  const profileName = (id: string | null) =>
    profiles.find((p) => p.id === id)?.name ?? id ?? '—';

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-semibold">Execution history</h2>
        <select
          className="px-2 py-1.5 bg-bg-tertiary border border-border rounded text-sm"
          value={profileFilter}
          onChange={(e) => setProfileFilter(e.target.value)}
        >
          <option value="">All profiles</option>
          {profiles.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
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
              <span
                className={`font-medium ${r.status === 'success' ? 'text-success' : 'text-error'}`}
              >
                {r.status}
              </span>
              <span className="text-text-muted">{new Date(r.fired_at).toLocaleString()}</span>
              <span>{profileName(r.profile_id)}</span>
              <span style={{ color: CHANNEL_COLORS[r.channel] ?? undefined }}>{r.channel}</span>
              <span className="flex-1 min-w-0 truncate">{r.label}</span>
              {r.error && <span className="w-full text-error text-xs">{r.error}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
