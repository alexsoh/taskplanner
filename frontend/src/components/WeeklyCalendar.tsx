import type { CalendarEvent } from '../types.ts';
import { CHANNEL_COLORS, DAY_NAMES } from '../utils/notifications.ts';

type Props = {
  events: CalendarEvent[];
  weekStart: Date;
};

function timeToMins(hhmm: string): number {
  const [h, m] = hhmm.split(':').map(Number);
  return (h ?? 0) * 60 + (m ?? 0);
}

export default function WeeklyCalendar({ events, weekStart }: Props) {
  const days: Date[] = [];
  for (let i = 0; i < 7; i++) {
    const d = new Date(weekStart);
    d.setDate(d.getDate() + i);
    days.push(d);
  }

  const byDay: CalendarEvent[][] = Array.from({ length: 7 }, () => []);
  for (const ev of events) {
    const dateStr = new Date(ev.occurrence_utc).toISOString().slice(0, 10);
    const idx = days.findIndex((day) => day.toISOString().slice(0, 10) === dateStr);
    if (idx >= 0) byDay[idx].push(ev);
  }

  for (let i = 0; i < 7; i++) {
    byDay[i].sort((a, b) => timeToMins(a.time) - timeToMins(b.time));
  }

  return (
    <div className="grid grid-cols-7 gap-2 min-h-[280px]">
      {days.map((day, i) => (
        <div key={i} className="flex flex-col border border-border rounded-lg overflow-hidden bg-bg-secondary">
          <div className="px-2 py-1.5 text-xs font-semibold text-text-secondary border-b border-border bg-bg-tertiary">
            {DAY_NAMES[i]} {day.getMonth() + 1}/{day.getDate()}
          </div>
          <div className="flex-1 p-1 space-y-1 overflow-y-auto max-h-64">
            {byDay[i].length === 0 ? (
              <p className="text-xs text-text-muted p-1">—</p>
            ) : (
              byDay[i].map((ev) => (
                <div
                  key={`${ev.action_id}-${ev.occurrence_utc}`}
                  className="text-xs px-1.5 py-1 rounded border border-border/60 truncate"
                  style={{ borderLeftColor: ev.profile_color, borderLeftWidth: 3 }}
                  title={`${ev.label} (${ev.channel})`}
                >
                  <span className="font-mono text-text-muted">{ev.time}</span>{' '}
                  <span style={{ color: CHANNEL_COLORS[ev.channel] ?? '#94a3b8' }}>{ev.channel}</span>
                  <div className="truncate text-text-primary">{ev.label}</div>
                </div>
              ))
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
