import { useEffect, useState } from 'react';
import * as api from '../api/client.ts';
import type { Profile } from '../types.ts';

type Props = {
  selectedId: string | null;
  onSelect: (id: string | null) => void;
};

export default function ProfilesPage({ selectedId, onSelect }: Props) {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [error, setError] = useState('');
  const [newName, setNewName] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState('');

  const load = () => api.listProfiles().then(setProfiles).catch((e) => setError(String(e)));

  useEffect(() => {
    load();
  }, []);

  const add = async () => {
    if (!newName.trim()) return;
    await api.createProfile({ name: newName.trim(), timezone: Intl.DateTimeFormat().resolvedOptions().timeZone });
    setNewName('');
    load();
  };

  const startEdit = (p: Profile) => {
    setEditingId(p.id);
    setEditingName(p.name);
  };

  const saveEdit = async () => {
    if (!editingName.trim() || !editingId) return;
    await api.updateProfile(editingId, { name: editingName.trim() });
    setEditingId(null);
    setEditingName('');
    load();
  };

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold text-text-primary">Profiles</h2>
      {error && <p className="text-sm text-error">{error}</p>}
      <div className="flex gap-2">
        <input
          className="flex-1 px-3 py-2 bg-bg-tertiary border border-border rounded text-sm"
          placeholder="New profile name"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && add()}
        />
        <button type="button" onClick={add} className="px-4 py-2 bg-accent text-bg-primary rounded text-sm font-medium">
          Add
        </button>
      </div>
      <ul className="space-y-2">
        {profiles.map((p) => (
          <li
            key={p.id}
            className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
              selectedId === p.id ? 'border-accent bg-bg-tertiary' : 'border-border bg-bg-secondary hover:bg-bg-tertiary'
            }`}
            onClick={() => onSelect(p.id)}
          >
            <span className="w-3 h-3 rounded-full shrink-0" style={{ background: p.color }} />
            <div className="flex-1 min-w-0">
              {editingId === p.id ? (
                <input
                  type="text"
                  className="w-full px-2 py-1 bg-bg-secondary border border-accent rounded text-sm font-medium"
                  value={editingName}
                  onChange={(e) => setEditingName(e.target.value)}
                  onClick={(e) => e.stopPropagation()}
                  onKeyDown={(e) => {
                    e.stopPropagation();
                    if (e.key === 'Enter') saveEdit();
                    if (e.key === 'Escape') setEditingId(null);
                  }}
                  autoFocus
                />
              ) : (
                <>
                  <div className="font-medium truncate">{p.name}</div>
                  <div className="text-xs text-text-muted">{p.timezone}</div>
                </>
              )}
            </div>
            <label className="flex items-center gap-1 text-xs" onClick={(e) => e.stopPropagation()}>
              <input
                type="checkbox"
                checked={p.enabled}
                onChange={async (e) => {
                  await api.updateProfile(p.id, { enabled: e.target.checked });
                  load();
                }}
              />
              On
            </label>
            {editingId === p.id ? (
              <>
                <button
                  type="button"
                  className="text-xs text-accent px-2"
                  onClick={(e) => {
                    e.stopPropagation();
                    saveEdit();
                  }}
                >
                  Save
                </button>
                <button
                  type="button"
                  className="text-xs text-text-muted px-2"
                  onClick={(e) => {
                    e.stopPropagation();
                    setEditingId(null);
                  }}
                >
                  Cancel
                </button>
              </>
            ) : (
              <>
                <button
                  type="button"
                  className="text-xs text-text-muted px-2"
                  onClick={(e) => {
                    e.stopPropagation();
                    startEdit(p);
                  }}
                >
                  Edit
                </button>
                <button
                  type="button"
                  className="text-xs text-error px-2"
                  onClick={async (e) => {
                    e.stopPropagation();
                    if (!confirm(`Delete profile "${p.name}"?`)) return;
                    await api.deleteProfile(p.id);
                    if (selectedId === p.id) onSelect(null);
                    load();
                  }}
                >
                  Delete
                </button>
              </>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
