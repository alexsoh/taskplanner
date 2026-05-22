import { describe, expect, it } from 'vitest';

function mondayOfWeek(d: Date): Date {
  const x = new Date(d);
  const day = (x.getDay() + 6) % 7;
  x.setDate(x.getDate() - day);
  x.setHours(0, 0, 0, 0);
  return x;
}

describe('mondayOfWeek', () => {
  it('returns Monday for a Wednesday', () => {
    const wed = new Date(2026, 4, 20);
    const mon = mondayOfWeek(wed);
    expect(mon.getDay()).toBe(1);
    expect(mon.getDate()).toBe(18);
  });
});
