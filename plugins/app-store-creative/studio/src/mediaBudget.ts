export type MediaBudget = { schema_version: number; status: string; configured_limit_bytes: number | null; current_payload_bytes: number | null; observed_payload_bytes: number; candidate_id: string | null; candidate_payload_bytes: number | null; forecast_payload_bytes: number | null; unverified_deliveries: { id: string; reason: string }[]; git_history_bytes: null; remote_storage_bytes: null; writes_performed: false; scope: string; reason?: string };
export function parseMediaBudget(value: unknown, expectedCandidate?: string | null): MediaBudget {
  const fail = () => { throw new Error('Invalid media budget observation'); };
  if (!value || typeof value !== 'object') return fail();
  const row = value as MediaBudget;
  const bytes = (v: unknown) => Number.isSafeInteger(v) && Number(v) >= 0;
  if (row.schema_version !== 1 || row.writes_performed !== false || row.git_history_bytes !== null || row.remote_storage_bytes !== null || !row.scope || typeof row.scope !== 'string' || !bytes(row.observed_payload_bytes) || ![row.configured_limit_bytes, row.current_payload_bytes, row.candidate_payload_bytes, row.forecast_payload_bytes].every(v => v === null || bytes(v)) || !(row.candidate_id === null || typeof row.candidate_id === 'string' && row.candidate_id.length > 0) || !Array.isArray(row.unverified_deliveries) || row.unverified_deliveries.some(item => !item || typeof item.id !== 'string' || !item.id || typeof item.reason !== 'string' || !item.reason)) return fail();
  if (expectedCandidate !== undefined && row.candidate_id !== expectedCandidate) return fail();
  if (row.status === 'UNKNOWN') {
    if (row.current_payload_bytes !== null || row.forecast_payload_bytes !== null) return fail();
  } else {
    if (row.unverified_deliveries.length || row.current_payload_bytes !== row.observed_payload_bytes || row.current_payload_bytes === null || row.forecast_payload_bytes !== row.current_payload_bytes + (row.candidate_payload_bytes ?? 0) || (row.candidate_id === null) !== (row.candidate_payload_bytes === null)) return fail();
    const expected = row.configured_limit_bytes === null ? 'NOT_CONFIGURED' : row.forecast_payload_bytes! > row.configured_limit_bytes ? 'OVER_BUDGET' : 'WITHIN_BUDGET';
    if (row.status !== expected) return fail();
  }
  return row;
}
