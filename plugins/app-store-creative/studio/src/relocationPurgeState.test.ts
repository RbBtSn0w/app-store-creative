import { expect, it } from 'vitest';
import { parsePurgePlan } from './relocationPurgeState';
it('binds unexecuted deletion to the selected quarantine and disjoint recovery paths', () => {
  const file = { path: '/tmp/retained', sha256: 'a'.repeat(64), size_bytes: 42 };
  const recovery = { ...file, path: '/tmp/active' };
  const plan = { id: 'b'.repeat(32), quarantine_id: 'c'.repeat(32), operation: 'relocation-purge-plan', purge_executed: false, files: [file], recovery: [recovery] };
  expect(parsePurgePlan(plan, plan.quarantine_id)).toEqual(plan);
  for (const value of [null, { ...plan, quarantine_id: 'wrong' }, { ...plan, purge_executed: true }, { ...plan, files: [] }, { ...plan, recovery: [] }, { ...plan, recovery: [file] }, { ...plan, files: [file, file] }, { ...plan, files: [{ ...file, size_bytes: -1 }] }]) expect(() => parsePurgePlan(value, plan.quarantine_id)).toThrow();
});
it('requires exact recovery hash and size coverage without duplicate recovery identities', () => {
  const file = { path: '/tmp/retained', sha256: 'a'.repeat(64), size_bytes: 42 };
  const recovery = { ...file, path: '/tmp/active' };
  const plan = { id: 'b'.repeat(32), quarantine_id: 'c'.repeat(32), operation: 'relocation-purge-plan', purge_executed: false, files: [file], recovery: [recovery] };
  for (const value of [
    { ...plan, recovery: [{ ...recovery, sha256: 'd'.repeat(64) }] },
    { ...plan, recovery: [{ ...recovery, size_bytes: 41 }] },
    { ...plan, recovery: [recovery, { ...recovery, path: '/tmp/other' }] },
  ]) expect(() => parsePurgePlan(value, plan.quarantine_id)).toThrow();
});
