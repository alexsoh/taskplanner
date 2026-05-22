import { useEffect, useState } from 'react';
import * as api from '../api/client.ts';
import type { AppSettings } from '../types.ts';

export default function SettingsPage() {
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    api.getSettings().then(setSettings).catch((e) => setError(String(e)));
  }, []);

  const save = async () => {
    if (!settings) return;
    setStatus('Saving…');
    try {
      const s = await api.updateSettings(settings);
      setSettings(s);
      setStatus('Saved');
    } catch (e) {
      setStatus('');
      setError(String(e));
    }
  };

  if (!settings) return <p className="text-text-muted text-sm">Loading…</p>;

  const mqtt = settings.mqtt;
  const tg = settings.telegram;

  return (
    <div className="space-y-6 max-w-xl">
      <h2 className="text-lg font-semibold">Settings</h2>
      {error && <p className="text-sm text-error">{error}</p>}

      <section className="space-y-3 p-4 border border-border rounded-lg bg-bg-secondary">
        <h3 className="font-medium">MQTT</h3>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={mqtt.enabled}
            onChange={(e) =>
              setSettings({ ...settings, mqtt: { ...mqtt, enabled: e.target.checked } })
            }
          />
          Enabled
        </label>
        <label className="block text-sm space-y-1">
          Broker
          <input
            className="w-full px-2 py-1.5 bg-bg-tertiary border border-border rounded"
            value={mqtt.broker}
            onChange={(e) => setSettings({ ...settings, mqtt: { ...mqtt, broker: e.target.value } })}
          />
        </label>
        <label className="block text-sm space-y-1">
          Port
          <input
            type="number"
            className="w-full px-2 py-1.5 bg-bg-tertiary border border-border rounded"
            value={mqtt.port}
            onChange={(e) =>
              setSettings({ ...settings, mqtt: { ...mqtt, port: parseInt(e.target.value, 10) || 1883 } })
            }
          />
        </label>
        <label className="block text-sm space-y-1">
          Username
          <input
            className="w-full px-2 py-1.5 bg-bg-tertiary border border-border rounded"
            value={mqtt.username}
            onChange={(e) => setSettings({ ...settings, mqtt: { ...mqtt, username: e.target.value } })}
          />
        </label>
        <label className="block text-sm space-y-1">
          Password
          <input
            type="password"
            className="w-full px-2 py-1.5 bg-bg-tertiary border border-border rounded"
            value={mqtt.password}
            onChange={(e) => setSettings({ ...settings, mqtt: { ...mqtt, password: e.target.value } })}
          />
        </label>
      </section>

      <section className="space-y-3 p-4 border border-border rounded-lg bg-bg-secondary">
        <h3 className="font-medium">Telegram</h3>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={tg.enabled}
            onChange={(e) =>
              setSettings({ ...settings, telegram: { ...tg, enabled: e.target.checked } })
            }
          />
          Enabled (outbound notifications)
        </label>
        <label className="block text-sm space-y-1">
          Bot token
          <input
            type="password"
            className="w-full px-2 py-1.5 bg-bg-tertiary border border-border rounded"
            value={tg.token}
            onChange={(e) => setSettings({ ...settings, telegram: { ...tg, token: e.target.value } })}
          />
        </label>
      </section>

      <button type="button" onClick={save} className="px-4 py-2 bg-accent text-bg-primary rounded text-sm font-medium">
        Save settings
      </button>
      {status && <p className="text-xs text-text-muted">{status}</p>}
    </div>
  );
}
