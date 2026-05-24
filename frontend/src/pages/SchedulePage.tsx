import { useCallback, useEffect, useState } from 'react';
import * as api from '../api/client.ts';
import NotificationForm from '../components/NotificationForm.tsx';
import WeeklyCalendar from '../components/WeeklyCalendar.tsx';
import type { CalendarEvent, NotificationChannel, Profile, ScheduledAction } from '../types.ts';
import { CHANNEL_COLORS, DAY_NAMES, defaultNotificationForChannel } from '../utils/notifications.ts';
import { browserTimezone, formatProfileTimezone } from '../utils/timezone.ts';

type Props = {
  profiles: Profile[];
  selectedId: string | null;
  onSelectProfile: (id: string | null) => void;
  onOpenHistory: (profileId: string | null) => void;
};

function mondayOfWeek(d: Date): Date {
  const x = new Date(d);
  const day = (x.getDay() + 6) % 7;
  x.setDate(x.getDate() - day);
  x.setHours(0, 0, 0, 0);
  return x;
}

export default function SchedulePage({
  profiles,
  selectedId,
  onSelectProfile,
  onOpenHistory,
}: Props) {
  const [actions, setActions] = useState<ScheduledAction[]>([]);
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [weekStart, setWeekStart] = useState(() => mondayOfWeek(new Date()));
  const [editing, setEditing] = useState<ScheduledAction | null>(null);
  const [draft, setDraft] = useState<{
    label: string;
    day_of_week: number;
    time: string;
    channel: NotificationChannel;
    notification_config: Record<string, unknown>;
  } | null>(null);
  const [testMsg, setTestMsg] = useState('');
  const [error, setError] = useState('');

  const profile = profiles.find((p) => p.id === selectedId) ?? null;
  const profileTimezoneLabel = profile ? formatProfileTimezone(profile.timezone) : '';
  const browserTz = browserTimezone();
  const timezoneDiffersFromBrowser = profile ? browserTz !== profile.timezone : false;

  const load = useCallback(async () => {
    if (!profile) return;
    setError('');
    try {
      const a = await api.listActions(profile.id);
      setActions(a);
      const from = weekStart.toISOString().slice(0, 10);
      const toDate = new Date(weekStart);
      toDate.setDate(toDate.getDate() + 6);
      const to = toDate.toISOString().slice(0, 10);
      const ev = await api.getCalendar(from, to, profile.id);
      setEvents(ev);
    } catch (e) {
      setError(String(e));
    }
  }, [profile, weekStart]);

  useEffect(() => {
    load();
  }, [load]);

  if (!profile) {
    return (
      <div className="space-y-4 max-w-6xl">
        <p className="text-text-muted text-sm">Select a profile to manage schedules.</p>
      </div>
    );
  }

  const startNew = (channel: NotificationChannel) => {
    setEditing(null);
    setDraft({
      label: 'New action',
      day_of_week: 1,
      time: '09:00',
      channel,
      notification_config: defaultNotificationForChannel(channel) as unknown as Record<string, unknown>,
    });
  };

  const startEdit = (a: ScheduledAction) => {
    setEditing(a);
    setDraft({
      label: a.label,
      day_of_week: a.day_of_week,
      time: a.time,
      channel: a.channel,
      notification_config: { ...a.notification_config },
    });
  };

  const save = async () => {
    if (!draft || !profile) return;
    try {
      if (editing) {
        await api.updateAction(editing.id, draft);
      } else {
        await api.createAction(profile.id, draft);
      }
      setDraft(null);
      setEditing(null);
      load();
    } catch (e) {
      setError(String(e));
    }
  };

  const shiftWeek = (delta: number) => {
    const n = new Date(weekStart);
    n.setDate(n.getDate() + delta * 7);
    setWeekStart(n);
  };

  return (
    <div className="space-y-6">
      {/* Header with profile selector and history link */}
      <div className="space-y-3">
        <h2 className="text-2xl font-bold text-text-primary">Schedules</h2>
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-2">
            <label className="text-sm font-medium text-text-secondary">Profile:</label>
            <select
              value={selectedId ?? ''}
              onChange={(e) => onSelectProfile(e.target.value || null)}
              className="px-3 py-1.5 bg-bg-tertiary border border-border rounded text-sm"
            >
              <option value="">Select a profile...</option>
              {profiles.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
          <button
            type="button"
            onClick={() => onOpenHistory(selectedId)}
            className="text-sm text-accent hover:text-accent/80 transition-colors underline"
          >
            View execution history →
          </button>
        </div>
        <div className="rounded-lg border border-border bg-bg-secondary px-3 py-2 text-sm">
          <span className="text-text-muted">Schedule timezone: </span>
          <span className="font-medium text-text-primary">{profileTimezoneLabel}</span>
          {timezoneDiffersFromBrowser && (
            <span className="text-text-muted">
              {' '}
              — your browser is {formatProfileTimezone(browserTz)}; times below are not in your local timezone.
            </span>
          )}
        </div>
      </div>

      {error && <p className="text-sm text-error">{error}</p>}

      {/* Week navigation */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex gap-2 items-center">
          <button
            type="button"
            className="px-2 py-1 text-sm border border-border rounded hover:bg-bg-tertiary transition-colors"
            onClick={() => shiftWeek(-1)}
          >
            ←
          </button>
          <span className="text-sm text-text-muted">
            Week of {weekStart.toLocaleDateString()}
          </span>
          <button
            type="button"
            className="px-2 py-1 text-sm border border-border rounded hover:bg-bg-tertiary transition-colors"
            onClick={() => shiftWeek(1)}
          >
            →
          </button>
        </div>
      </div>

      <WeeklyCalendar events={events} weekStart={weekStart} timezoneLabel={profileTimezoneLabel} />

      <div className="flex flex-wrap gap-2">
        {(['evalex', 'mqtt', 'telegram', 'http', 'script', 'nvr'] as NotificationChannel[]).map((ch) => (
          <button
            key={ch}
            type="button"
            className="px-3 py-1.5 text-xs rounded border border-border hover:bg-bg-tertiary transition-colors"
            style={{ color: CHANNEL_COLORS[ch] }}
            onClick={() => startNew(ch)}
          >
            + {ch}
          </button>
        ))}
      </div>

      {draft && (
        <div className="p-4 border border-border rounded-lg bg-bg-secondary space-y-4">
          <h3 className="font-medium">{editing ? 'Edit action' : 'New action'}</h3>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <label className="text-sm space-y-1">
              Label
              <input
                className="w-full px-2 py-1.5 bg-bg-tertiary border border-border rounded text-sm"
                value={draft.label}
                onChange={(e) => setDraft({ ...draft, label: e.target.value })}
              />
            </label>
            <label className="text-sm space-y-1">
              Day
              <select
                className="w-full px-2 py-1.5 bg-bg-tertiary border border-border rounded text-sm"
                value={draft.day_of_week}
                onChange={(e) => setDraft({ ...draft, day_of_week: parseInt(e.target.value, 10) })}
              >
                {DAY_NAMES.map((d, i) => (
                  <option key={d} value={i}>
                    {d}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-sm space-y-1">
              <span>
                Time{' '}
                <span className="text-xs text-text-muted">({profileTimezoneLabel})</span>
              </span>
              <input
                type="time"
                className="w-full px-2 py-1.5 bg-bg-tertiary border border-border rounded text-sm"
                value={draft.time}
                onChange={(e) => setDraft({ ...draft, time: e.target.value })}
              />
            </label>
            <label className="text-sm space-y-1">
              Channel
              <span className="block px-2 py-1.5 text-sm capitalize">{draft.channel}</span>
            </label>
          </div>
          <NotificationForm
            channel={draft.channel}
            config={draft.notification_config}
            onChange={(c) => setDraft((prev) => (prev ? { ...prev, notification_config: c } : prev))}
          />
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={save} className="px-4 py-2 bg-accent text-bg-primary rounded text-sm">
              Save
            </button>
            <button
              type="button"
              onClick={() => {
                setDraft(null);
                setEditing(null);
              }}
              className="px-4 py-2 border border-border rounded text-sm"
            >
              Cancel
            </button>
            {editing && (
              <button
                type="button"
                className="px-4 py-2 border border-border rounded text-sm"
                onClick={async () => {
                  setTestMsg('Testing…');
                  try {
                    const r = await api.testAction(editing.id);
                    setTestMsg(r.message || r.status || 'OK');
                  } catch (e) {
                    setTestMsg(String(e));
                  }
                }}
              >
                Test now
              </button>
            )}
          </div>
          {testMsg && <p className="text-xs text-text-muted">{testMsg}</p>}
        </div>
      )}

      <div className="space-y-2">
        <h3 className="text-sm font-semibold text-text-secondary uppercase tracking-wide">
          All actions
          <span className="normal-case font-normal text-text-muted ml-2">({profileTimezoneLabel})</span>
        </h3>
        {actions.length === 0 ? (
          <p className="text-sm text-text-muted">No scheduled actions yet.</p>
        ) : (
          <ul className="space-y-1">
            {actions.map((a) => (
              <li
                key={a.id}
                className="flex items-center gap-2 p-2 rounded border border-border bg-bg-secondary text-sm cursor-pointer hover:bg-bg-tertiary"
                onClick={() => startEdit(a)}
              >
                <span className="font-mono text-text-muted w-24">
                  {DAY_NAMES[a.day_of_week]} {a.time}
                </span>
                <span style={{ color: CHANNEL_COLORS[a.channel] }}>{a.channel}</span>
                <span className="flex-1 truncate">{a.label}</span>
                {!a.enabled && <span className="text-xs text-text-muted">off</span>}
                <button
                  type="button"
                  className="text-xs text-text-muted hover:text-text-primary transition-colors"
                  onClick={async (e) => {
                    e.stopPropagation();
                    try {
                      await api.copyAction(a.id);
                      load();
                    } catch (err) {
                      setError(`Failed to copy action: ${err}`);
                    }
                  }}
                  title="Copy action"
                >
                  Copy
                </button>
                <button
                  type="button"
                  className="text-xs text-error"
                  onClick={async (e) => {
                    e.stopPropagation();
                    if (!confirm('Delete this action?')) return;
                    await api.deleteAction(a.id);
                    load();
                  }}
                >
                  Delete
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
