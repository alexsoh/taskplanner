import type { ReactNode } from 'react';
import { useState } from 'react';
import * as api from '../api/client.ts';
import type { NotificationChannel } from '../types.ts';

type Props = {
  channel: NotificationChannel;
  config: Record<string, unknown>;
  onChange: (config: Record<string, unknown>) => void;
};

function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="block space-y-1 text-sm">
      <span className="text-text-muted">{label}</span>
      {children}
    </label>
  );
}

const inputCls =
  'w-full px-2 py-1.5 bg-bg-tertiary border border-border rounded text-sm focus:outline-none focus:border-border-focus';

export default function NotificationForm({ channel, config, onChange }: Props) {
  const set = (k: string, v: unknown) => onChange({ ...config, [k]: v });

  if (channel === 'mqtt') {
    return (
      <div className="space-y-3">
        <Field label="Topic">
          <input className={inputCls} value={String(config.topic ?? '')} onChange={(e) => set('topic', e.target.value)} />
        </Field>
        <Field label="Payload">
          <select className={inputCls} value={String(config.payload ?? 'json')} onChange={(e) => set('payload', e.target.value)}>
            <option value="json">json</option>
            <option value="image">image</option>
            <option value="both">both</option>
          </select>
        </Field>
        <Field label="Message mode">
          <select className={inputCls} value={String(config.messageMode ?? 'raw')} onChange={(e) => set('messageMode', e.target.value)}>
            <option value="raw">raw</option>
            <option value="template">template</option>
            <option value="simple">simple</option>
          </select>
        </Field>
        <Field label="Template">
          <textarea className={inputCls + ' min-h-20'} value={String(config.template ?? '')} onChange={(e) => set('template', e.target.value)} />
        </Field>
      </div>
    );
  }

  if (channel === 'telegram') {
    return (
      <div className="space-y-3">
        <Field label="Chat ID">
          <input className={inputCls} value={String(config.chatId ?? '')} onChange={(e) => set('chatId', e.target.value)} />
        </Field>
        <Field label="Message mode">
          <select className={inputCls} value={String(config.messageMode ?? 'raw')} onChange={(e) => set('messageMode', e.target.value)}>
            <option value="raw">raw</option>
            <option value="template">template</option>
            <option value="simple">simple</option>
          </select>
        </Field>
        <Field label="Template">
          <textarea className={inputCls + ' min-h-20'} value={String(config.template ?? '')} onChange={(e) => set('template', e.target.value)} />
        </Field>
      </div>
    );
  }

  if (channel === 'http') {
    return (
      <div className="space-y-3">
        <Field label="URL">
          <input className={inputCls} value={String(config.url ?? '')} onChange={(e) => set('url', e.target.value)} />
        </Field>
        <Field label="Method">
          <select className={inputCls} value={String(config.method ?? 'POST')} onChange={(e) => set('method', e.target.value)}>
            <option value="GET">GET</option>
            <option value="POST">POST</option>
            <option value="PUT">PUT</option>
          </select>
        </Field>
        <Field label="Auth">
          <select className={inputCls} value={String(config.authType ?? 'none')} onChange={(e) => set('authType', e.target.value)}>
            <option value="none">none</option>
            <option value="basic">basic</option>
            <option value="digest">digest</option>
            <option value="bearer">bearer</option>
          </select>
        </Field>
        <Field label="Template">
          <textarea className={inputCls + ' min-h-20'} value={String(config.template ?? '')} onChange={(e) => set('template', e.target.value)} />
        </Field>
      </div>
    );
  }

  if (channel === 'script') {
    return (
      <div className="space-y-3">
        <Field label="Script path">
          <input className={inputCls} value={String(config.scriptPath ?? '')} onChange={(e) => set('scriptPath', e.target.value)} />
        </Field>
        <Field label="Timeout (seconds)">
          <input
            type="number"
            className={inputCls}
            value={Number(config.timeoutSeconds ?? 120)}
            onChange={(e) => set('timeoutSeconds', parseInt(e.target.value, 10) || 120)}
          />
        </Field>
        <Field label="Arguments (one per line)">
          <textarea
            className={inputCls + ' min-h-16 font-mono text-xs'}
            value={(Array.isArray(config.argumentTemplates) ? config.argumentTemplates : []).join('\n')}
            onChange={(e) =>
              set(
                'argumentTemplates',
                e.target.value.split('\n').filter((l) => l.trim()),
              )
            }
          />
        </Field>
      </div>
    );
  }

  if (channel === 'evalex') {
    const [discovering, setDiscovering] = useState(false);
    const [discoveryError, setDiscoveryError] = useState<string | null>(null);
    const [discoveredCameras, setDiscoveredCameras] = useState<Array<{ id: string; name: string }>>([]);

    const handleDiscover = async () => {
      const app = String(config.app ?? 'vizmux');
      const serverAddress = String(config.serverAddress ?? '');

      if (!serverAddress.trim()) {
        setDiscoveryError('Server address is required');
        return;
      }

      setDiscovering(true);
      setDiscoveryError(null);

      try {
        const result = await api.discoverCameras(app, serverAddress);
        setDiscoveredCameras(result.cameras);
        if (result.cameras.length === 0) {
          setDiscoveryError('No cameras found');
        }
      } catch (err) {
        setDiscoveryError(
          err instanceof Error ? err.message : 'Failed to discover cameras. Check server address and ensure the app is running.',
        );
        setDiscoveredCameras([]);
      } finally {
        setDiscovering(false);
      }
    };

    return (
      <div className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <Field label="App">
            <select
              className={inputCls}
              value={String(config.app ?? 'vizmux')}
              onChange={(e) => {
                set('app', e.target.value);
                setDiscoveredCameras([]);
                setDiscoveryError(null);
              }}
            >
              <option value="vizmux">VizMux</option>
              <option value="piyoai">PiyoAI</option>
              <option value="vizrec">VizRec</option>
            </select>
          </Field>
          <Field label="Server Address">
            <input
              className={inputCls}
              placeholder="http://localhost:8000"
              value={String(config.serverAddress ?? '')}
              onChange={(e) => {
                set('serverAddress', e.target.value);
                setDiscoveredCameras([]);
                setDiscoveryError(null);
              }}
            />
          </Field>
        </div>
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-sm">
            <span className="text-text-muted">Cameras</span>
            <button
              type="button"
              disabled={discovering || !String(config.serverAddress ?? '').trim()}
              onClick={handleDiscover}
              className="text-xs px-2 py-0.5 bg-bg-secondary border border-border rounded hover:bg-bg-hover disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {discovering ? 'Discovering...' : 'Discover'}
            </button>
          </div>
          {discoveryError && <p className="text-xs text-text-error">{discoveryError}</p>}
          {discoveredCameras.length > 0 && (
            <select
              multiple
              className={inputCls + ' min-h-24'}
              value={Array.isArray(config.cameraIds) ? config.cameraIds : []}
              onChange={(e) => set('cameraIds', Array.from(e.currentTarget.selectedOptions, (o) => o.value))}
            >
              {discoveredCameras.map((cam) => (
                <option key={cam.id} value={cam.id}>
                  {cam.name ? `${cam.name} (${cam.id})` : cam.id}
                </option>
              ))}
            </select>
          )}
        </div>
        <Field label="Action">
          <div className="space-y-2">
            <label className="flex items-center space-x-2 cursor-pointer">
              <input
                type="radio"
                name="action"
                value="enable"
                checked={config.action === 'enable'}
                onChange={() => set('action', 'enable')}
                className="w-4 h-4"
              />
              <span className="text-sm">Enable</span>
            </label>
            <label className="flex items-center space-x-2 cursor-pointer">
              <input
                type="radio"
                name="action"
                value="disable"
                checked={config.action === 'disable'}
                onChange={() => set('action', 'disable')}
                className="w-4 h-4"
              />
              <span className="text-sm">Disable</span>
            </label>
          </div>
        </Field>
      </div>
    );
  }

  // nvr
  return (
    <div className="space-y-3">
      <Field label="Brand">
        <select className={inputCls} value={String(config.brand ?? 'reolink')} onChange={(e) => set('brand', e.target.value)}>
          <option value="reolink">reolink</option>
          <option value="hikvision">hikvision</option>
          <option value="dahua">dahua</option>
          <option value="ezviz">ezviz</option>
          <option value="blueiris">blueiris</option>
        </select>
      </Field>
      <Field label="Base URL">
        <input className={inputCls} value={String(config.baseUrl ?? '')} onChange={(e) => set('baseUrl', e.target.value)} />
      </Field>
      <Field label="Username">
        <input className={inputCls} value={String(config.httpUsername ?? '')} onChange={(e) => set('httpUsername', e.target.value)} />
      </Field>
      <Field label="Password">
        <input type="password" className={inputCls} value={String(config.httpPassword ?? '')} onChange={(e) => set('httpPassword', e.target.value)} />
      </Field>
      <Field label="Channel">
        <input
          type="number"
          className={inputCls}
          value={Number(config.channel ?? 0)}
          onChange={(e) => set('channel', parseInt(e.target.value, 10) || 0)}
        />
      </Field>
    </div>
  );
}
