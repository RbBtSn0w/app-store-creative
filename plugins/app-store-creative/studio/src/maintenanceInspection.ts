export type MaintenanceInspection = { id: string; status: string; phase: string; execution_verified: boolean; errors: string[] };
export function parseMaintenanceInspection(value: unknown, id: string): MaintenanceInspection {
  if (!value || typeof value !== 'object') throw new Error('Invalid execution observation');
  const row = value as Record<string, unknown>;
  if (row.id !== id || !['PASS', 'FAIL', 'UNKNOWN', 'INCOMPLETE', 'NOT_EXECUTED'].includes(String(row.status)) || typeof row.phase !== 'string' || !row.phase.trim() || row.remote_write !== false || typeof row.execution_verified !== 'boolean' || row.execution_verified !== (row.status === 'PASS') || !Array.isArray(row.errors) || row.errors.some(error => typeof error !== 'string')) throw new Error('Invalid execution observation');
  return row as MaintenanceInspection;
}
