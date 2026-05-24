import type { ReactNode } from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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

function savedCameraIds(config: Record<string, unknown>): string[] {
  if (!Array.isArray(config.cameraIds)) return [];
  return config.cameraIds.map((id) => String(id).trim()).filter(Boolean);
}

function savedCameraLabels(config: Record<string, unknown>): Record<string, string> {
  const raw = config.cameraLabels;
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {};
  return Object.fromEntries(
    Object.entries(raw as Record<string, unknown>)
      .map(([id, name]) => [id.trim(), String(name).trim()] as const)
      .filter(([id, name]) => id && name),
  );
}

function formatCameraLabel(id: string, name: string): string {
  const trimmed = name.trim();
  if (trimmed && trimmed !== id) return trimmed;
  return 'Unnamed camera';
}

export default function NotificationForm({ channel, config, onChange }: Props) {
  const configRef = useRef(config);
  configRef.current = config;
  const set = (k: string, v: unknown) => onChange({ ...configRef.current, [k]: v });

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
    const [camerasExpanded, setCamerasExpanded] = useState(false);
    const selectedIds = savedCameraIds(config);
    const cameraLabels = savedCameraLabels(config);

    const handleDiscover = useCallback(async (expandOnSuccess = false) => {
      const app = String(configRef.current.app ?? 'vizmux');
      const serverAddress = String(configRef.current.serverAddress ?? '').trim();

      if (!serverAddress) {
        setDiscoveryError('Server address is required');
        setDiscoveredCameras([]);
        return;
      }

      setDiscovering(true);
      setDiscoveryError(null);

      try {
        const result = await api.discoverCameras(app, serverAddress);
        setDiscoveredCameras(result.cameras);
        if (result.cameras.length === 0) {
          setDiscoveryError('No cameras found');
        } else if (expandOnSuccess) {
          setCamerasExpanded(true);
        }
      } catch (err) {
        setDiscoveryError(
          err instanceof Error ? err.message : 'Failed to discover cameras. Check server address and ensure the app is running.',
        );
        setDiscoveredCameras([]);
      } finally {
        setDiscovering(false);
      }
    }, []);

    useEffect(() => {
      const serverAddress = String(config.serverAddress ?? '').trim();
      if (!serverAddress) {
        setDiscoveredCameras([]);
        setDiscoveryError(null);
        return;
      }
      const timer = window.setTimeout(() => {
        void handleDiscover();
      }, 300);
      return () => window.clearTimeout(timer);
    }, [config.app, config.serverAddress, handleDiscover]);

    useEffect(() => {
      if (discoveredCameras.length === 0 || selectedIds.length === 0) return;
      const labels = savedCameraLabels(configRef.current);
      let changed = false;
      const nextLabels = { ...labels };
      for (const id of selectedIds) {
        if (nextLabels[id]) continue;
        const cam = discoveredCameras.find((c) => c.id === id);
        if (cam?.name && cam.name !== id) {
          nextLabels[id] = cam.name;
          changed = true;
        }
      }
      if (changed) {
        onChange({ ...configRef.current, cameraLabels: nextLabels });
      }
    }, [discoveredCameras, onChange, selectedIds]);

    const discoveredNames = useMemo(() => {
      const names = new Map<string, string>();
      for (const cam of discoveredCameras) {
        if (cam.id) names.set(cam.id, cam.name || cam.id);
      }
      return names;
    }, [discoveredCameras]);

    const labelForCamera = (id: string) => cameraLabels[id] || discoveredNames.get(id) || id;

    const selectedCsv = useMemo(
      () =>
        selectedIds
          .map((id) => formatCameraLabel(id, labelForCamera(id)))
          .filter((name) => name !== 'Unnamed camera')
          .join(', '),
      [selectedIds, cameraLabels, discoveredNames],
    );

    const toggleCamera = (cameraId: string, checked: boolean, cameraName?: string) => {
      const current = savedCameraIds(configRef.current);
      const labels = savedCameraLabels(configRef.current);
      if (checked) {
        const nextIds = [...current, cameraId].filter((id, index, all) => all.indexOf(id) === index);
        const nextLabels = { ...labels };
        const name = (cameraName || discoveredNames.get(cameraId) || '').trim();
        if (name && name !== cameraId) {
          nextLabels[cameraId] = name;
        }
        onChange({ ...configRef.current, cameraIds: nextIds, cameraLabels: nextLabels });
        return;
      }
      const nextIds = current.filter((id) => id !== cameraId);
      const nextLabels = { ...labels };
      delete nextLabels[cameraId];
      onChange({ ...configRef.current, cameraIds: nextIds, cameraLabels: nextLabels });
    };

    return (
      <div className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <Field label="App">
            <select
              className={inputCls}
              value={String(config.app ?? 'vizmux')}
              onChange={(e) => {
                onChange({ ...configRef.current, app: e.target.value, cameraIds: [], cameraLabels: {} });
                setDiscoveredCameras([]);
                setDiscoveryError(null);
                setCamerasExpanded(false);
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
                setDiscoveryError(null);
              }}
            />
          </Field>
        </div>
        <div className="space-y-2 text-sm">
          <div className="flex items-center gap-2 min-w-0">
            <button
              type="button"
              disabled={discoveredCameras.length === 0 && !discovering}
              onClick={() => setCamerasExpanded((open) => !open)}
              className="flex items-center gap-1.5 min-w-0 flex-1 text-left disabled:cursor-default"
              title={camerasExpanded ? 'Hide camera list' : 'Show camera list'}
            >
              <span className="text-text-muted shrink-0 w-3">{camerasExpanded ? '▾' : '▸'}</span>
              <span className="text-text-muted shrink-0">Cameras</span>
              {selectedIds.length > 0 ? (
                <span className="text-xs text-text-muted shrink-0">({selectedIds.length})</span>
              ) : null}
              {!camerasExpanded && selectedCsv ? (
                <span className="text-sm truncate min-w-0">{selectedCsv}</span>
              ) : !camerasExpanded && discoveredCameras.length > 0 ? (
                <span className="text-xs text-text-muted truncate min-w-0">
                  {discoveredCameras.length} available — click to select
                </span>
              ) : null}
            </button>
            <button
              type="button"
              disabled={discovering || !String(config.serverAddress ?? '').trim()}
              onClick={() => void handleDiscover(true)}
              className="shrink-0 text-xs px-2 py-1 bg-bg-secondary border border-border rounded hover:bg-bg-hover disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {discovering ? 'Discovering...' : 'Discover'}
            </button>
          </div>
          {discoveryError ? <p className="text-xs text-error">{discoveryError}</p> : null}
          {camerasExpanded && discoveredCameras.length > 0 ? (
            <div className="border border-border rounded p-2 bg-bg-tertiary space-y-1 max-h-48 overflow-y-auto">
              {discoveredCameras.map((cam) => {
                const isSelected = selectedIds.includes(cam.id);
                return (
                  <label key={cam.id} className="flex items-center gap-2 cursor-pointer hover:bg-bg-secondary p-1 rounded transition-colors">
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={(e) => toggleCamera(cam.id, e.target.checked, cam.name)}
                      className="w-4 h-4 accent-accent rounded"
                    />
                    <span className="text-sm">{formatCameraLabel(cam.id, cam.name ?? '')}</span>
                  </label>
                );
              })}
            </div>
          ) : discovering ? (
            <p className="text-xs text-text-muted">Loading cameras…</p>
          ) : null}
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
