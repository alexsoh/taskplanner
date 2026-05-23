import { useEffect, useState } from 'react';
import * as api from '../api/client.ts';
import type { AppSettings } from '../types.ts';
import { UpdateSection } from '../components/UpdateSection.tsx';

type SettingsTab = 'notifications' | 'server' | 'updates' | 'logs';

export default function SettingsPage() {
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');
  const [activeTab, setActiveTab] = useState<SettingsTab>('notifications');
  const [newIp, setNewIp] = useState('');
  const [addingIp, setAddingIp] = useState(false);
  const [addingClientIp, setAddingClientIp] = useState(false);
  const [logs, setLogs] = useState<{ taskplanner: string; upgrade: string }>({ taskplanner: '', upgrade: '' });
  const [loadingLogs, setLoadingLogs] = useState(false);

  useEffect(() => {
    api.getSettings().then(setSettings).catch((e) => setError(String(e)));
  }, []);

  const loadLogs = async () => {
    setLoadingLogs(true);
    try {
      const tpResult = await fetch('/api/logs/taskplanner').then(r => r.json());
      const upgResult = await fetch('/api/logs/upgrade').then(r => r.json()).catch(() => ({ content: '(upgrade log not available)' }));
      setLogs({
        taskplanner: tpResult.content || '',
        upgrade: upgResult.content || '',
      });
    } catch (e) {
      setError(`Failed to load logs: ${e}`);
    } finally {
      setLoadingLogs(false);
    }
  };

  const save = async () => {
    if (!settings) return;
    setStatus('Saving…');
    setError('');
    try {
      // Create a clean update payload that includes upgradeToken
      const updatePayload: Partial<AppSettings> = {
        mqtt: settings.mqtt,
        telegram: settings.telegram,
        upgradeToken: settings.upgradeToken,
        allowedIps: settings.allowedIps,
        serverPort: settings.serverPort,
      };
      const s = await api.updateSettings(updatePayload);
      setSettings(s);
      setStatus(`Saved successfully${s.upgradeToken ? ' (token persisted)' : ''}`);
      setTimeout(() => setStatus(''), 3000);
    } catch (e) {
      const errorMsg = String(e);
      setStatus('');
      setError(`Save failed: ${errorMsg}`);
    }
  };

  const handleAddIp = async () => {
    if (!newIp.trim()) {
      setError('IP/CIDR cannot be empty');
      return;
    }

    setAddingIp(true);
    setError('');
    try {
      if (!settings) return;
      const updatedIps = [...(settings.allowedIps || ['127.0.0.1', '::1']), newIp.trim()];
      const result = await api.updateAllowedIps(updatedIps);
      setSettings({ ...settings, allowedIps: result.allowedIps });
      setNewIp('');
      setStatus('IP added');
      setTimeout(() => setStatus(''), 2000);
    } catch (e) {
      setError(String(e));
    } finally {
      setAddingIp(false);
    }
  };

  const handleRemoveIp = async (ipToRemove: string) => {
    if (!settings?.allowedIps) return;
    try {
      const updatedIps = settings.allowedIps.filter((ip) => ip !== ipToRemove);
      const result = await api.updateAllowedIps(updatedIps);
      setSettings({ ...settings, allowedIps: result.allowedIps });
      setStatus('IP removed');
      setTimeout(() => setStatus(''), 2000);
    } catch (e) {
      setError(String(e));
    }
  };

  const handleAddClientIp = async () => {
    setAddingClientIp(true);
    setError('');
    try {
      // Detect public IP using api.ipify.org
      const response = await fetch('https://api.ipify.org?format=json', {
        signal: AbortSignal.timeout(8000),
        cache: 'no-store',
      });
      
      if (!response.ok) {
        setError(`Could not detect public IP (HTTP ${response.status}). Add it manually or try again.`);
        setAddingClientIp(false);
        return;
      }

      const data = await response.json() as { ip?: string };
      const ip = (data.ip || '').trim();

      if (!ip) {
        setError('Could not detect public IP — unexpected response. Add the address manually.');
        setAddingClientIp(false);
        return;
      }

      // Check if already in whitelist
      if (settings?.allowedIps?.includes(ip)) {
        setStatus('That address is already in the whitelist.');
        setAddingClientIp(false);
        return;
      }

      // Add the IP via API
      const result = await api.allowClientIp(ip);
      if (result.ok || result.added) {
        setSettings({ ...settings, allowedIps: result.allowedIps } as AppSettings);
        setStatus(`Added ${ip} to whitelist`);
        setTimeout(() => setStatus(''), 2000);
      } else {
        setStatus(result.message || 'IP already in whitelist');
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setAddingClientIp(false);
    }
  };

  const handleUpdatePort = async (newPort: number) => {
    if (newPort < 1 || newPort > 65535) {
      setError('Port must be between 1 and 65535');
      return;
    }
    setStatus('Updating…');
    try {
      const result = await api.updateServerPort(newPort);
      setSettings({ ...settings, serverPort: result.port } as AppSettings);
      setStatus(result.message);
    } catch (e) {
      setStatus('');
      setError(String(e));
    }
  };

  if (!settings) return <p className="text-text-muted text-sm">Loading…</p>;

  const mqtt = settings.mqtt;
  const tg = settings.telegram;
  const allowedIps = settings.allowedIps || ['127.0.0.1', '::1'];
  const serverPort = settings.serverPort || 8200;

  return (
    <div className="space-y-6 max-w-4xl">
      <h2 className="text-lg font-semibold">Settings</h2>
      {error && <p className="text-sm text-error">{error}</p>}

      {/* Tab Navigation */}
      <div className="flex gap-2 border-b border-border">
        <button
          onClick={() => setActiveTab('notifications')}
          className={`px-4 py-2 font-medium text-sm transition ${
            activeTab === 'notifications'
              ? 'border-b-2 border-accent text-accent'
              : 'text-text-muted hover:text-text'
          }`}
        >
          Notifications
        </button>
        <button
          onClick={() => setActiveTab('server')}
          className={`px-4 py-2 font-medium text-sm transition ${
            activeTab === 'server'
              ? 'border-b-2 border-accent text-accent'
              : 'text-text-muted hover:text-text'
          }`}
        >
          Server
        </button>
        <button
          onClick={() => setActiveTab('updates')}
          className={`px-4 py-2 font-medium text-sm transition ${
            activeTab === 'updates'
              ? 'border-b-2 border-accent text-accent'
              : 'text-text-muted hover:text-text'
          }`}
        >
          Updates
        </button>
        <button
          onClick={() => { setActiveTab('logs'); loadLogs(); }}
          className={`px-4 py-2 font-medium text-sm transition ${
            activeTab === 'logs'
              ? 'border-b-2 border-accent text-accent'
              : 'text-text-muted hover:text-text'
          }`}
        >
          Logs
        </button>
      </div>

      {/* Notifications Tab */}
      {activeTab === 'notifications' && (
        <div className="space-y-6">
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
        </div>
      )}

      {/* Server Tab */}
      {activeTab === 'server' && (
        <div className="space-y-6">
          <section className="space-y-3 p-4 border border-border rounded-lg bg-bg-secondary">
            <h3 className="font-medium">Port Configuration</h3>
            <label className="block text-sm space-y-1">
              Server Port
              <input
                type="number"
                min="1"
                max="65535"
                className="w-full px-2 py-1.5 bg-bg-tertiary border border-border rounded"
                value={serverPort}
                onChange={(e) => {
                  const port = parseInt(e.target.value, 10);
                  setSettings({ ...settings, serverPort: port });
                }}
              />
            </label>
            <p className="text-xs text-text-muted">
              Requires server restart to take effect
            </p>
            <button
              type="button"
              onClick={() => handleUpdatePort(serverPort)}
              className="px-3 py-1.5 bg-bg-tertiary border border-border rounded hover:bg-bg-quaternary text-sm font-medium transition"
            >
              Update Port
            </button>
          </section>

          <section className="space-y-3 p-4 border border-border rounded-lg bg-bg-secondary">
            <h3 className="font-medium">IP Whitelist</h3>
            {allowedIps.length === 0 && (
              <p className="text-sm text-warning">Warning: Whitelist is empty - all IPs are allowed</p>
            )}
            <div className="space-y-2">
              <div className="space-y-2">
                <label className="block text-xs text-text-muted">Additional IPs</label>
                <div className="flex flex-wrap gap-2">
                  {allowedIps.filter((ip) => ip !== '127.0.0.1' && ip !== '::1').map((ip) => (
                    <div
                      key={ip}
                      className="inline-flex items-center gap-2 px-3 py-1.5 bg-bg-tertiary border border-border rounded text-sm"
                    >
                      <code className="font-mono">{ip}</code>
                      <button
                        type="button"
                        onClick={() => handleRemoveIp(ip)}
                        className="ml-2 text-text-muted hover:text-error transition"
                        title="Remove IP"
                      >
                        ×
                      </button>
                    </div>
                  ))}
                  {allowedIps.filter((ip) => ip !== '127.0.0.1' && ip !== '::1').length === 0 && (
                    <p className="text-xs text-text-muted italic">None</p>
                  )}
                </div>
              </div>

              <details className="text-sm">
                <summary className="cursor-pointer text-text-muted hover:text-text transition font-medium">
                  Advanced (Loopback - always allowed)
                </summary>
                <div className="mt-2 pl-4 space-y-2 border-l border-border">
                  <div className="flex flex-wrap gap-2">
                    {allowedIps.filter((ip) => ip === '127.0.0.1' || ip === '::1').map((ip) => (
                      <div
                        key={ip}
                        className="inline-flex items-center gap-2 px-3 py-1.5 bg-bg-tertiary border border-border rounded text-sm opacity-60"
                      >
                        <code className="font-mono">{ip}</code>
                      </div>
                    ))}
                  </div>
                  <p className="text-xs text-text-muted italic">Loopback addresses cannot be removed</p>
                </div>
              </details>
            </div>

            <label className="block text-sm space-y-1">
              Add IP or CIDR
              <div className="flex gap-2">
                <input
                  className="flex-1 px-2 py-1.5 bg-bg-tertiary border border-border rounded"
                  placeholder="192.168.1.100 or 10.0.0.0/24"
                  value={newIp}
                  onChange={(e) => setNewIp(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleAddIp();
                  }}
                />
                <button
                  type="button"
                  onClick={handleAddIp}
                  disabled={addingIp}
                  className="px-3 py-1.5 bg-accent text-bg-primary rounded hover:opacity-90 text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed transition"
                >
                  {addingIp ? 'Adding…' : 'Add'}
                </button>
              </div>
            </label>

            <button
              type="button"
              onClick={handleAddClientIp}
              disabled={addingClientIp}
              className="px-3 py-1.5 bg-bg-tertiary border border-border rounded hover:bg-bg-quaternary text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed transition"
            >
              {addingClientIp ? 'Detecting…' : 'Add my internet IP to whitelist'}
            </button>
            <p className="text-xs text-text-muted">
              Uses a public lookup; VPNs or blockers may change the result.
            </p>
          </section>
        </div>
      )}

      {/* Updates Tab */}
      {activeTab === 'updates' && (
        <UpdateSection
          upgradeToken={settings.upgradeToken}
          onTokenChange={(token) => setSettings({ ...settings, upgradeToken: token })}
        />
      )}

      {/* Logs Tab */}
      {activeTab === 'logs' && (
        <div className="space-y-4">
          <div className="space-y-2">
            <button
              type="button"
              onClick={loadLogs}
              disabled={loadingLogs}
              className="px-4 py-2 bg-accent text-bg-primary rounded text-sm font-medium disabled:opacity-50"
            >
              {loadingLogs ? 'Loading...' : 'Refresh Logs'}
            </button>
          </div>

          <div className="space-y-2">
            <h3 className="font-medium">TaskPlanner Log</h3>
            <pre className="bg-bg-tertiary border border-border rounded p-3 text-xs overflow-auto max-h-64 font-mono">
              {logs.taskplanner || '(no logs)'}
            </pre>
          </div>

          <div className="space-y-2">
            <h3 className="font-medium">Upgrade Log</h3>
            <pre className="bg-bg-tertiary border border-border rounded p-3 text-xs overflow-auto max-h-64 font-mono">
              {logs.upgrade || '(no logs)'}
            </pre>
          </div>
        </div>
      )}

      {/* Bottom Save Button */}
      {activeTab !== 'logs' && (
        <div className="space-y-2 pt-4 border-t border-border">
          <button
            type="button"
            onClick={save}
            className="px-4 py-2 bg-accent text-bg-primary rounded text-sm font-medium"
          >
            Save settings
          </button>
          {status && <p className="text-xs text-text-muted">{status}</p>}
        </div>
      )}
    </div>
  );
}
