export type PurgeFile = { path: string; sha256: string; size_bytes: number };
export type PurgePlan = { id: string; files: PurgeFile[]; recovery: PurgeFile[] };
export function parsePurgePlan(value: unknown, expectedOperationId: string): PurgePlan {
  if (!value || typeof value !== 'object') throw new Error('Invalid purge plan');
  const record = value as Record<string, unknown>;
  if (typeof record.id !== 'string' || !/^[a-z0-9]+$/.test(record.id) || record.quarantine_id !== expectedOperationId || record.operation !== 'relocation-purge-plan' || record.purge_executed !== false || !Array.isArray(record.files) || !record.files.length || !Array.isArray(record.recovery) || !record.recovery.length) throw new Error('Invalid purge plan');
  const paths = new Set<string>();
  for (const file of [...record.files, ...record.recovery]) {
    if (!file || typeof file.path !== 'string' || !file.path.trim() || paths.has(file.path) || typeof file.sha256 !== 'string' || !/^[0-9a-f]{64}$/.test(file.sha256) || !Number.isSafeInteger(file.size_bytes) || file.size_bytes < 0) throw new Error('Invalid purge file');
    paths.add(file.path);
  }
  const recovery = new Map<string, number>();
  for (const file of record.recovery) {
    if (recovery.has(file.sha256)) throw new Error('Duplicate recovery identity');
    recovery.set(file.sha256, file.size_bytes);
  }
  const deletedHashes = new Set<string>();
  for (const file of record.files) {
    if (recovery.get(file.sha256) !== file.size_bytes) throw new Error('Missing exact independent recovery object');
    deletedHashes.add(file.sha256);
  }
  if (deletedHashes.size !== recovery.size) throw new Error('Unbound recovery object');
  return record as PurgePlan;
}
