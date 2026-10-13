export type RelocatedObjects = { id: string; status: string; object_integrity_verified: boolean; checked_files: number; errors: string[]; scope: string };
export function parseRelocatedObjects(value: unknown, id: string): RelocatedObjects {
  if (!value || typeof value !== 'object') throw new Error('Invalid copied-object observation');
  const row = value as Record<string, unknown>;
  if (row.id !== id || !['PASS', 'FAIL', 'UNKNOWN', 'INCOMPLETE'].includes(String(row.status)) || typeof row.object_integrity_verified !== 'boolean' || row.object_integrity_verified !== (row.status === 'PASS') || !Number.isSafeInteger(row.checked_files) || Number(row.checked_files) < 0 || (row.status === 'PASS' && Number(row.checked_files) === 0) || row.remote_write !== false || typeof row.scope !== 'string' || !row.scope.trim() || !Array.isArray(row.errors) || row.errors.some(error => typeof error !== 'string')) throw new Error('Invalid copied-object observation');
  return row as RelocatedObjects;
}
