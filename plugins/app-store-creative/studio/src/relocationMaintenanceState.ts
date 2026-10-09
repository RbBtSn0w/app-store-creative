export type CopyFile = { path: string; sha256: string; size_bytes: number; decision: string; reason: string };
export type CopyPlan = { id: string; operation: 'relocation-retention-plan'; cleanup_executed: false; files: CopyFile[] };
export function parseCopyPlan(value: unknown): CopyPlan {
  if (!value || typeof value !== 'object') throw new Error('Invalid retention plan');
  const plan = value as Record<string, unknown>;
  if (typeof plan.id !== 'string' || !/^[a-z0-9]+$/.test(plan.id) || plan.operation !== 'relocation-retention-plan' || plan.cleanup_executed !== false || !Array.isArray(plan.files)) throw new Error('Invalid retention plan');
  const paths = new Set<string>();
  for (const file of plan.files) {
    if (!file || typeof file.path !== 'string' || !file.path.trim() || paths.has(file.path) || typeof file.sha256 !== 'string' || !/^[0-9a-f]{64}$/.test(file.sha256) || !Number.isSafeInteger(file.size_bytes) || file.size_bytes < 0 || !['eligible', 'protected'].includes(file.decision) || typeof file.reason !== 'string' || !file.reason.trim()) throw new Error('Invalid retained file');
    paths.add(file.path);
  }
  return plan as CopyPlan;
}
export function copyDispositionAllowed(phase: string, status: string, action: string): boolean {
  if (action === 'resume') return ['PREPARING', 'INTERRUPTED'].includes(phase) && ['VERIFIED', 'PARTIAL'].includes(status);
  if (action === 'cancel') return ['PREPARING', 'INTERRUPTED', 'PREPARED'].includes(phase) && ['VERIFIED', 'PARTIAL'].includes(status);
  if (status !== 'VERIFIED') return false;
  if (action === 'commit') return ['PREPARED', 'COMMIT_STARTED'].includes(phase);
  if (action === 'restore') return ['QUARANTINED', 'RESTORING'].includes(phase);
  return false;
}
