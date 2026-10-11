import { expect, it } from 'vitest';
import { parseCopyPlan } from './relocationMaintenanceState';
it('requires an unexecuted relocation retention plan with complete unique file identities', () => {
  const file = { path: '/tmp/source/object', sha256: 'a'.repeat(64), size_bytes: 42, decision: 'eligible', reason: 'verified-independent-object' };
  const plan = { id: 'b'.repeat(32), operation: 'relocation-retention-plan', cleanup_executed: false, files: [file] };
  expect(parseCopyPlan(plan)).toEqual(plan);
  for (const value of [null, { ...plan, operation: 'cleanup-plan' }, { ...plan, cleanup_executed: true }, { ...plan, files: [file, file] }, { ...plan, files: [{ ...file, path: '' }] }, { ...plan, files: [{ ...file, size_bytes: -1 }] }]) expect(() => parseCopyPlan(value)).toThrow();
});

import { copyDispositionAllowed } from './relocationMaintenanceState';
it('limits dispositions to independently observed phases', () => {
  expect(copyDispositionAllowed('PREPARED', 'VERIFIED', 'commit')).toBe(true);
  expect(copyDispositionAllowed('QUARANTINED', 'VERIFIED', 'restore')).toBe(true);
  for (const phase of ['PURGED', 'INTERRUPTED', 'RESTORED']) {
    expect(copyDispositionAllowed(phase, 'VERIFIED', 'commit')).toBe(false);
    expect(copyDispositionAllowed(phase, 'VERIFIED', 'restore')).toBe(false);
  }
  expect(copyDispositionAllowed('PREPARED', 'CHANGED', 'commit')).toBe(false);
  expect(copyDispositionAllowed('QUARANTINED', 'VERIFIED', 'purge')).toBe(false);
});
it('allows explicit interrupted preparation recovery while blocking changed evidence', () => {
  expect(copyDispositionAllowed('INTERRUPTED', 'PARTIAL', 'resume')).toBe(true);
  expect(copyDispositionAllowed('PREPARING', 'PARTIAL', 'cancel')).toBe(true);
  expect(copyDispositionAllowed('PREPARED', 'VERIFIED', 'cancel')).toBe(true);
  expect(copyDispositionAllowed('COMMIT_STARTED', 'VERIFIED', 'commit')).toBe(true);
  expect(copyDispositionAllowed('RESTORING', 'VERIFIED', 'restore')).toBe(true);
  expect(copyDispositionAllowed('INTERRUPTED', 'IDENTITY_CONFLICT', 'resume')).toBe(false);
  expect(copyDispositionAllowed('QUARANTINED', 'VERIFIED', 'cancel')).toBe(false);
});
