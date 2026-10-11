export type ArtifactPolicy = { schema_version: number; trialRetentionDays: number; diagnosticRetentionDays: number; quarantineDays: number; mediaBudgetBytes: number | null };
export function parseArtifactPolicy(value: unknown): ArtifactPolicy {
  if (!value || typeof value !== 'object') throw new Error('Invalid project retention settings');
  const row = value as Record<string, unknown>; const policy = row.policy as ArtifactPolicy;
  if (row.schema_version !== 1 || row.writes_performed !== false || !['project', 'defaults'].includes(String(row.source)) || typeof row.policy_sha256 !== 'string' || !/^[0-9a-f]{64}$/.test(row.policy_sha256) || !policy || policy.schema_version !== 1 || [policy.trialRetentionDays, policy.diagnosticRetentionDays, policy.quarantineDays].some(days => !Number.isSafeInteger(days) || days < 0) || (policy.mediaBudgetBytes !== null && (!Number.isSafeInteger(policy.mediaBudgetBytes) || policy.mediaBudgetBytes < 0))) throw new Error('Invalid project retention settings');
  return policy;
}
export async function readArtifactPolicy(): Promise<ArtifactPolicy> {
  const response = await fetch('/api/storage/artifact-policy', { cache: 'no-store' });
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || 'Project retention settings failed');
  return parseArtifactPolicy(value);
}
