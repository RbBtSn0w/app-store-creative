export type MaintenanceObject = { sha256: string; size_bytes: number };
export type MaintenanceRecord = { id: string; operation: string; objects: MaintenanceObject[]; recorded_status?: string | null };
export function parseMaintenance(value: unknown): MaintenanceRecord {
  if (!value || typeof value !== 'object') throw new Error('Invalid maintenance record');
  const record = value as Record<string, unknown>;
  if (typeof record.id !== 'string' || !/^[a-z0-9]+$/.test(record.id) || typeof record.operation !== 'string' || !Array.isArray(record.objects)) throw new Error('Invalid maintenance identity');
  for (const object of record.objects) {
    if (!object || typeof object !== 'object' || !/^[0-9a-f]{64}$/.test(object.sha256) || !Number.isSafeInteger(object.size_bytes) || object.size_bytes < 0) throw new Error('Invalid maintenance object');
  }
  if (record.recorded_status !== undefined && record.recorded_status !== null && typeof record.recorded_status !== 'string') throw new Error('Invalid maintenance status');
  return record as MaintenanceRecord;
}
export function maintenanceAllowed(busy: boolean, unresolved: boolean, reviewed: boolean, actor: string, reason: string): boolean {
  return !busy && !unresolved && reviewed && actor.trim().length > 0 && reason.trim().length > 0;
}

export function purgeAllowed(busy: boolean, unresolved: boolean, reviewed: boolean, actor: string, reason: string, confirmation: string): boolean {
  return maintenanceAllowed(busy, unresolved, reviewed, actor, reason) && confirmation === 'PURGE';
}
