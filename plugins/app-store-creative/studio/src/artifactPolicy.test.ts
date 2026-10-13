import { expect, it } from 'vitest';
import { parseArtifactPolicy } from './artifactPolicy';
it('accepts versioned observed policy and refuses guessed or invalid defaults', () => {
  const policy = { schema_version: 1, trialRetentionDays: 3, diagnosticRetentionDays: 14, quarantineDays: 2, mediaBudgetBytes: null };
  const row = { schema_version: 1, policy, source: 'project', policy_sha256: 'a'.repeat(64), writes_performed: false };
  expect(parseArtifactPolicy(row)).toEqual(policy);
  for (const changed of [{ ...row, writes_performed: true }, { ...row, source: 'guessed' }, { ...row, policy_sha256: '' }, { ...row, policy: { ...policy, schema_version: 2 } }, { ...row, policy: { ...policy, quarantineDays: -1 } }, { ...row, policy: { ...policy, trialRetentionDays: true } }, { ...row, policy: { ...policy, mediaBudgetBytes: -1 } }]) expect(() => parseArtifactPolicy(changed)).toThrow();
});
