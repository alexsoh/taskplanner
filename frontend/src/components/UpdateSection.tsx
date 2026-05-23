import { useEffect, useState } from 'react';
import * as api from '../api/client.ts';
import type { UpdateCheckResponse } from '../types.ts';

interface UpdateSectionProps {
  upgradeToken?: string;
  onTokenChange?: (token: string) => void;
}

export function UpdateSection({
  upgradeToken = '',
  onTokenChange,
}: UpdateSectionProps) {
  const [token, setToken] = useState(upgradeToken);
  const [checkResult, setCheckResult] = useState<UpdateCheckResponse | null>(null);
  const [checking, setChecking] = useState(false);
  const [installing, setInstalling] = useState(false);
  const [statusMsg, setStatusMsg] = useState('');
  const [error, setError] = useState('');
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [logPath, setLogPath] = useState('');

  // Poll version during upgrade
  useEffect(() => {
    if (!installing) return;

    let pollCount = 0;
    const maxPolls = 180; // 3 minutes / 3 seconds = 180 polls

    const pollTimer = setInterval(async () => {
      pollCount += 1;
      setElapsedSeconds((prev) => prev + 3);

      if (pollCount > maxPolls) {
        setStatusMsg('Polling timed out after 3 minutes');
        setInstalling(false);
        clearInterval(pollTimer);
        return;
      }

      try {
        const ver = await api.getVersion();
        if (checkResult && ver.version > checkResult.currentVersion) {
          setStatusMsg('Update completed successfully');
          setInstalling(false);
          clearInterval(pollTimer);
        }
      } catch {
        // Server may be down during upgrade, continue polling
      }
    }, 3000);

    // Initial 5s delay before first poll
    const delayTimer = setTimeout(() => {
      // Timer started, first poll happens after initial interval
    }, 5000);

    return () => {
      clearInterval(pollTimer);
      clearTimeout(delayTimer);
    };
  }, [installing, checkResult]);

  const handleSaveToken = () => {
    if (onTokenChange) {
      onTokenChange(token);
    }
    setStatusMsg('Token saved');
    setTimeout(() => setStatusMsg(''), 3000);
  };

  const handleCheckForUpdates = async () => {
    if (!token) {
      setError('Token is required');
      return;
    }

    setChecking(true);
    setError('');
    setStatusMsg('Checking for updates…');

    try {
      const result = await api.checkForUpdate(token);
      if (result.error) {
        setError(result.error);
      } else {
        setCheckResult(result);
        if (result.updateAvailable) {
          setStatusMsg(`Update available: ${result.latestVersion}`);
        } else {
          setStatusMsg('You are already on the latest version');
        }
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setChecking(false);
    }
  };

  const handleInstall = async () => {
    if (!token) {
      setError('Token is required');
      return;
    }

    const confirmed = window.confirm('Start update installation? The app will restart.');
    if (!confirmed) return;

    setInstalling(true);
    setError('');
    setStatusMsg('Starting upgrade…');
    setElapsedSeconds(0);

    try {
      const result = await api.installUpdate(token);
      setLogPath(result.logPath);
      setStatusMsg('Upgrade in progress. Waiting for app to restart…');
    } catch (e) {
      setError(String(e));
      setInstalling(false);
    }
  };

  const getTokenExpiry = () => {
    if (!checkResult?.tokenExpiresAt) return null;

    const expiryDate = new Date(checkResult.tokenExpiresAt);
    const now = new Date();
    const daysUntilExpiry = Math.ceil((expiryDate.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));

    if (daysUntilExpiry < 0) {
      return <p className="text-sm text-error">Token expired</p>;
    } else if (daysUntilExpiry <= 30) {
      return <p className="text-sm text-warning">Token expires in {daysUntilExpiry} days</p>;
    }
    return null;
  };

  return (
    <section className="space-y-3 p-4 border border-border rounded-lg bg-bg-secondary">
      <h3 className="font-medium">Update</h3>

      {error && <p className="text-sm text-error">{error}</p>}

      <label className="block text-sm space-y-1">
        Download Token
        <div className="flex gap-2">
          <input
            type="password"
            className="flex-1 px-2 py-1.5 bg-bg-tertiary border border-border rounded"
            placeholder="evlx_..."
            value={token}
            onChange={(e) => setToken(e.target.value)}
          />
          <button
            type="button"
            onClick={handleSaveToken}
            className="px-3 py-1.5 bg-bg-tertiary border border-border rounded hover:bg-bg-quaternary text-sm font-medium transition"
          >
            Save
          </button>
        </div>
      </label>

      <div className="flex gap-2 pt-2">
        <button
          type="button"
          onClick={handleCheckForUpdates}
          disabled={!token || checking || installing}
          className="px-3 py-1.5 bg-accent text-bg-primary rounded text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed hover:opacity-90 transition"
        >
          {checking ? 'Checking…' : 'Check for Updates'}
        </button>

        {checkResult?.updateAvailable && (
          <button
            type="button"
            onClick={handleInstall}
            disabled={installing}
            className="px-3 py-1.5 bg-accent text-bg-primary rounded text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed hover:opacity-90 transition"
          >
            {installing ? 'Installing…' : 'Install Update'}
          </button>
        )}
      </div>

      {checkResult && !checkResult.error && (
        <div className="mt-4 space-y-2 text-sm border-t border-border pt-3">
          <p>
            <span className="font-medium">Current:</span> {checkResult.currentVersion}
          </p>
          <p>
            <span className="font-medium">Latest:</span> {checkResult.latestVersion}
          </p>
          {checkResult.changeSummary && (
            <p>
              <span className="font-medium">Changes:</span> {checkResult.changeSummary}
            </p>
          )}
          {getTokenExpiry()}
        </div>
      )}

      {statusMsg && <p className="text-xs text-text-muted">{statusMsg}</p>}

      {installing && elapsedSeconds > 0 && (
        <p className="text-xs text-text-muted">Elapsed: {elapsedSeconds}s</p>
      )}

      {logPath && (
        <p className="text-xs text-text-muted">
          Log: <code className="bg-bg-tertiary px-1">{logPath}</code>
        </p>
      )}
    </section>
  );
}
