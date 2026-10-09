import { describe, expect, it } from 'vitest';
import { maintenanceAllowed, purgeAllowed, parseMaintenance } from './maintenanceState';
describe('maintenance review', () => {
  it('requires exact typed permanent deletion confirmation in addition to reviewed authorization', () => {
    expect(purgeAllowed(false, false, true, 'owner', 'expired trials', 'PURGE')).toBe(true);
    expect(purgeAllowed(false, false, true, 'owner', 'expired trials', '')).toBe(false);
    expect(purgeAllowed(false, false, true, 'owner', 'expired trials', 'purge')).toBe(false);
    expect(purgeAllowed(false, false, false, 'owner', 'expired trials', 'PURGE')).toBe(false);
    expect(purgeAllowed(false, true, true, 'owner', 'expired trials', 'PURGE')).toBe(false);
  });
  it('requires explicit review, operator and reason, and stops on unknown outcome', () => {
    expect(maintenanceAllowed(false, false, true, 'owner', 'retire trial')).toBe(true);
    expect(maintenanceAllowed(false, false, false, 'owner', 'retire trial')).toBe(false);
    expect(maintenanceAllowed(false, true, true, 'owner', 'retire trial')).toBe(false);
    expect(maintenanceAllowed(true, false, true, 'owner', 'retire trial')).toBe(false);
    expect(maintenanceAllowed(false, false, true, ' ', 'retire trial')).toBe(false);
    expect(maintenanceAllowed(false, false, true, 'owner', ' ')).toBe(false);
  });
  it('refuses malformed identities or object sizes before offering execution', () => {
    const record = { id: 'a'.repeat(32), operation: 'cleanup-plan', objects: [{ sha256: 'b'.repeat(64), size_bytes: 42 }] };
    expect(parseMaintenance(record)).toEqual(record);
    expect(() => parseMaintenance({ ...record, id: '../outside' })).toThrow();
    expect(() => parseMaintenance({ ...record, objects: [{ sha256: 'b'.repeat(64), size_bytes: -1 }] })).toThrow();
  });
});
