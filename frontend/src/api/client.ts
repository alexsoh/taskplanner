import type {
  AppSettings,
  CalendarEvent,
  ExecutionRun,
  NotificationChannel,
  Profile,
  ScheduledAction,
  UpdateCheckResponse,
} from '../types.ts';

/** Same-origin API prefix or full backend URL; read at call time so embed ``config.js`` can run before the first request. */
export function getApiBase(): string {
  return ((window as any).__TASKPLANNER_CONFIG__?.apiBaseUrl as string) ?? '';
}

async function json<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ error: resp.statusText }));
    throw new Error((err as { error?: string }).error || resp.statusText);
  }
  return resp.json() as Promise<T>;
}

export async function listProfiles(): Promise<Profile[]> {
  return json(await fetch(`${getApiBase()}/api/profiles`));
}

export async function createProfile(body: Partial<Profile>): Promise<Profile> {
  return json(
    await fetch(`${getApiBase()}/api/profiles`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  );
}

export async function updateProfile(id: string, body: Partial<Profile>): Promise<Profile> {
  return json(
    await fetch(`${getApiBase()}/api/profiles/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  );
}

export async function deleteProfile(id: string): Promise<void> {
  await json(await fetch(`${getApiBase()}/api/profiles/${id}`, { method: 'DELETE' }));
}

export async function copyProfile(id: string, body: Partial<Profile>): Promise<Profile> {
  return json(
    await fetch(`${getApiBase()}/api/profiles/${id}/copy`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  );
}

export async function listActions(profileId: string): Promise<ScheduledAction[]> {
  return json(await fetch(`${getApiBase()}/api/profiles/${profileId}/actions`));
}

export async function createAction(
  profileId: string,
  body: {
    label: string;
    day_of_week: number;
    time: string;
    channel: NotificationChannel;
    enabled?: boolean;
    notification_config: Record<string, unknown>;
  },
): Promise<ScheduledAction> {
  return json(
    await fetch(`${getApiBase()}/api/profiles/${profileId}/actions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  );
}

export async function updateAction(
  id: string,
  body: Partial<ScheduledAction>,
): Promise<ScheduledAction> {
  return json(
    await fetch(`${getApiBase()}/api/actions/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  );
}

export async function deleteAction(id: string): Promise<void> {
  await json(await fetch(`${getApiBase()}/api/actions/${id}`, { method: 'DELETE' }));
}

export async function testAction(id: string): Promise<{ status: string; message?: string; error?: string }> {
  const resp = await fetch(`${getApiBase()}/api/actions/${id}/test`, { method: 'POST' });
  return json(resp);
}

export async function getCalendar(from: string, to: string, profileId?: string): Promise<CalendarEvent[]> {
  const q = new URLSearchParams({ from, to });
  if (profileId) q.set('profile_id', profileId);
  return json(await fetch(`${getApiBase()}/api/calendar?${q}`));
}

export async function listExecutions(params?: {
  from?: string;
  to?: string;
  profile_id?: string;
  limit?: number;
}): Promise<ExecutionRun[]> {
  const q = new URLSearchParams();
  if (params?.from) q.set('from', params.from);
  if (params?.to) q.set('to', params.to);
  if (params?.profile_id) q.set('profile_id', params.profile_id);
  if (params?.limit) q.set('limit', String(params.limit));
  const qs = q.toString();
  return json(await fetch(`${getApiBase()}/api/executions${qs ? `?${qs}` : ''}`));
}

export async function getSettings(): Promise<AppSettings> {
  return json(await fetch(`${getApiBase()}/api/settings`));
}

export async function updateSettings(body: Partial<AppSettings>): Promise<AppSettings> {
  return json(
    await fetch(`${getApiBase()}/api/settings`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  );
}

export async function discoverCameras(app: string, serverAddress: string): Promise<{ cameras: Array<{ id: string; name: string }> }> {
  return json(
    await fetch(`${getApiBase()}/api/discover/cameras`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ app, serverAddress }),
    }),
  );
}

export async function getVersion(): Promise<{ version: string }> {
  return json(await fetch(`${getApiBase()}/api/version`));
}

export async function checkForUpdate(token: string): Promise<UpdateCheckResponse> {
  return json(
    await fetch(`${getApiBase()}/api/update/check`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token }),
    }),
  );
}

export async function installUpdate(token: string): Promise<{ status: string; logPath: string }> {
  return json(
    await fetch(`${getApiBase()}/api/update/install`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token }),
    }),
  );
}

export async function getServerConfig(): Promise<{ port: number; allowedIps: string[] }> {
  return json(await fetch(`${getApiBase()}/api/server/config`));
}

export async function updateAllowedIps(allowedIps: string[]): Promise<{ ok: boolean; allowedIps: string[] }> {
  return json(
    await fetch(`${getApiBase()}/api/server/allowed-ips`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ allowedIps }),
    }),
  );
}

export async function updateServerPort(port: number): Promise<{ ok: boolean; port: number; message: string }> {
  return json(
    await fetch(`${getApiBase()}/api/server/port`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ port }),
    }),
  );
}

export async function allowClientIp(ip: string): Promise<{ ok?: boolean; added: boolean; ip: string; message?: string; allowedIps: string[] }> {
  return json(
    await fetch(`${getApiBase()}/api/server/allow-client-ip`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ip }),
    }),
  );
}
