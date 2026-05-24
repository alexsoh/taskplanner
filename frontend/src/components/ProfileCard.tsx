import { useState } from 'react';
import type { Profile } from '../types.ts';

interface Props {
  profile: Profile;
  isSelected: boolean;
  isMenuOpen: boolean;
  onMenuToggle: (id: string) => void;
  onSelectProfile: (id: string) => void;
  onToggleEnabled: (id: string, enabled: boolean) => Promise<void>;
  onStartEdit: (profile: Profile) => void;
  onCopy: (profile: Profile) => Promise<void>;
  onDelete: (id: string, name: string) => Promise<void>;
}

export default function ProfileCard({
  profile,
  isSelected,
  isMenuOpen,
  onMenuToggle,
  onSelectProfile,
  onToggleEnabled,
  onStartEdit,
  onCopy,
  onDelete,
}: Props) {
  const [isTogglingEnabled, setIsTogglingEnabled] = useState(false);

  const handleToggleEnabled = async () => {
    setIsTogglingEnabled(true);
    try {
      await onToggleEnabled(profile.id, !profile.enabled);
    } finally {
      setIsTogglingEnabled(false);
    }
  };

  const closeMenu = () => onMenuToggle('');
  const openMenu = () => onMenuToggle(profile.id);

  return (
    <div
      onClick={() => onSelectProfile(profile.id)}
      className={`relative p-4 rounded-lg border cursor-pointer transition-all duration-300 ${
        isSelected
          ? 'border-accent bg-accent/10'
          : 'border-border bg-bg-secondary hover:bg-bg-tertiary hover:border-border'
      } ${!profile.enabled ? 'opacity-60' : ''}`}
    >
      {/* Card content */}
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <span
            className={`w-3 h-3 rounded-full shrink-0 transition-opacity ${
              !profile.enabled ? 'opacity-50' : ''
            }`}
            style={{ background: profile.color }}
          />
          <div className="flex-1 min-w-0">
            <div className="font-medium truncate text-text-primary">{profile.name}</div>
            <div className="text-xs text-text-muted truncate">{profile.timezone}</div>
          </div>
        </div>

        {/* Disabled badge */}
        {!profile.enabled && (
          <div className="text-xs font-medium text-text-muted bg-bg-tertiary/50 w-fit px-2 py-1 rounded">
            Disabled
          </div>
        )}
      </div>

      {/* Menu button */}
      <div
        className="absolute top-2 right-2 relative"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          onClick={() => {
            isMenuOpen ? closeMenu() : openMenu();
          }}
          className="p-1 text-text-muted hover:text-text-primary hover:bg-bg-tertiary rounded transition-colors"
          title="Profile actions"
        >
          ⋮
        </button>

        {/* Dropdown menu */}
        {isMenuOpen && (
          <div className="absolute top-full left-0 pt-1 w-40 bg-bg-tertiary border border-border rounded-lg shadow-lg z-10">
            <button
              type="button"
              onClick={async (e) => {
                e.stopPropagation();
                await handleToggleEnabled();
                closeMenu();
              }}
              disabled={isTogglingEnabled}
              className="w-full text-left px-3 py-2 text-sm hover:bg-bg-quaternary transition-colors disabled:opacity-50"
            >
              {profile.enabled ? 'Disable' : 'Enable'}
            </button>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onStartEdit(profile);
                closeMenu();
              }}
              className="w-full text-left px-3 py-2 text-sm hover:bg-bg-quaternary transition-colors border-t border-border"
            >
              Edit
            </button>
            <button
              type="button"
              onClick={async (e) => {
                e.stopPropagation();
                await onCopy(profile);
                closeMenu();
              }}
              className="w-full text-left px-3 py-2 text-sm hover:bg-bg-quaternary transition-colors border-t border-border"
            >
              Copy
            </button>
            <button
              type="button"
              onClick={async (e) => {
                e.stopPropagation();
                if (!confirm(`Delete profile "${profile.name}"?`)) return;
                await onDelete(profile.id, profile.name);
                closeMenu();
              }}
              className="w-full text-left px-3 py-2 text-sm text-error hover:bg-bg-quaternary transition-colors border-t border-border"
            >
              Delete
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
