/** Human-readable profile timezone for schedule UI. */
export function formatProfileTimezone(tz: string): string {
  const name = (tz || 'UTC').trim() || 'UTC';
  try {
    const now = new Date();
    const offset = new Intl.DateTimeFormat('en-US', {
      timeZone: name,
      timeZoneName: 'shortOffset',
    })
      .formatToParts(now)
      .find((p) => p.type === 'timeZoneName')?.value;
    const abbrev = new Intl.DateTimeFormat('en-US', {
      timeZone: name,
      timeZoneName: 'short',
    })
      .formatToParts(now)
      .find((p) => p.type === 'timeZoneName')?.value;
    if (abbrev && offset && abbrev !== offset) {
      return `${name} (${abbrev}, ${offset})`;
    }
    if (offset) return `${name} (${offset})`;
    if (abbrev) return `${name} (${abbrev})`;
    return name;
  } catch {
    return name;
  }
}

export function browserTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch {
    return 'UTC';
  }
}
