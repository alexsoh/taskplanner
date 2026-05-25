import { useState } from 'react';
import * as api from '../api/client.ts';
import ProfileCard from '../components/ProfileCard.tsx';
import type { Profile } from '../types.ts';

type Props = {
  profiles: Profile[];
  selectedId: string | null;
  onProfilesChange: () => void;
  onSelectAndOpenSchedule: (id: string) => void;
};

export default function ProfilesPage({
  profiles,
  selectedId,
  onProfilesChange,
  onSelectAndOpenSchedule,
}: Props) {
  const [error, setError] = useState('');
  const [showAddModal, setShowAddModal] = useState(false);
  const [newName, setNewName] = useState('');
  const [isAdding, setIsAdding] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState('');
  const [openMenuId, setOpenMenuId] = useState<string>('');

  const add = async () => {
    if (!newName.trim()) return;
    setIsAdding(true);
    try {
      await api.createProfile({
        name: newName.trim(),
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      });
      setNewName('');
      setShowAddModal(false);
      onProfilesChange();
    } catch (e) {
      setError(String(e));
    } finally {
      setIsAdding(false);
    }
  };

  const saveEdit = async () => {
    if (!editingName.trim() || !editingId) return;
    try {
      await api.updateProfile(editingId, { name: editingName.trim() });
      setEditingId(null);
      setEditingName('');
      onProfilesChange();
    } catch (e) {
      setError(String(e));
    }
  };

  const doCopy = async (p: Profile) => {
    try {
      const copied = await api.copyProfile(p.id, { name: `${p.name} (Copy)` });
      onProfilesChange();
      // Select and open the new profile's schedules
      onSelectAndOpenSchedule(copied.id);
    } catch (e) {
      setError(String(e));
    }
  };

  const doDelete = async (id: string) => {
    try {
      await api.deleteProfile(id);
      onProfilesChange();
    } catch (e) {
      setError(String(e));
    }
  };

  const doToggleEnabled = async (id: string, enabled: boolean) => {
    try {
      await api.updateProfile(id, { enabled });
      onProfilesChange();
    } catch (e) {
      setError(String(e));
    }
  };

  const startEdit = (p: Profile) => {
    setEditingId(p.id);
    setEditingName(p.name);
    setOpenMenuId('');
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-text-primary">Profiles</h2>
        <button
          type="button"
          onClick={() => setShowAddModal(true)}
          className="px-3 py-1.5 bg-accent text-bg-primary rounded-lg text-sm font-medium hover:opacity-90 transition-opacity"
          title="Add new profile"
        >
          + Add Profile
        </button>
      </div>

      {error && <p className="text-sm text-error">{error}</p>}

      {/* Add Profile Modal */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => setShowAddModal(false)}>
          <div
            className="bg-bg-secondary border border-border rounded-lg p-6 w-full max-w-sm shadow-lg"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-lg font-semibold text-text-primary mb-4">Add Profile</h3>
            <div className="flex gap-2">
              <input
                type="text"
                className="flex-1 px-3 py-2 bg-bg-tertiary border border-border rounded text-sm"
                placeholder="Profile name"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') add();
                  if (e.key === 'Escape') setShowAddModal(false);
                }}
                autoFocus
              />
              <button
                type="button"
                onClick={add}
                disabled={isAdding || !newName.trim()}
                className="px-4 py-2 bg-accent text-bg-primary rounded text-sm font-medium hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed transition-opacity"
              >
                {isAdding ? 'Adding…' : 'Save'}
              </button>
            </div>
            <button
              type="button"
              onClick={() => setShowAddModal(false)}
              className="mt-3 w-full px-3 py-1.5 border border-border rounded text-sm hover:bg-bg-tertiary transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Edit Mode for selected profile */}
      {editingId && (
        <div className="p-4 border border-accent/30 bg-accent/5 rounded-lg space-y-3">
          <h3 className="font-medium text-text-primary">Edit Profile</h3>
          <input
            type="text"
            className="w-full px-3 py-2 bg-bg-tertiary border border-border rounded text-sm"
            value={editingName}
            onChange={(e) => setEditingName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') saveEdit();
              if (e.key === 'Escape') setEditingId(null);
            }}
            autoFocus
          />
          <div className="flex gap-2">
            <button
              type="button"
              onClick={saveEdit}
              className="px-3 py-1.5 bg-accent text-bg-primary rounded text-sm font-medium hover:opacity-90 transition-opacity"
            >
              Save
            </button>
            <button
              type="button"
              onClick={() => setEditingId(null)}
              className="px-3 py-1.5 border border-border rounded text-sm hover:bg-bg-tertiary transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Profile Cards Grid */}
      {profiles.length === 0 ? (
        <p className="text-sm text-text-muted">No profiles yet. Click "+ Add Profile" to create one.</p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {profiles.map((p) => (
            <ProfileCard
              key={p.id}
              profile={p}
              isSelected={selectedId === p.id}
              isMenuOpen={openMenuId === p.id}
              onMenuToggle={setOpenMenuId}
              onSelectProfile={onSelectAndOpenSchedule}
              onToggleEnabled={doToggleEnabled}
              onStartEdit={startEdit}
              onCopy={doCopy}
              onDelete={doDelete}
            />
          ))}
        </div>
      )}
    </div>
  );
}
