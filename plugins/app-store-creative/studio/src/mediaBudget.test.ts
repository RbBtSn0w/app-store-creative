import { expect, it } from 'vitest';
import { parseMediaBudget } from './mediaBudget';
const report = { schema_version: 1, status: 'OVER_BUDGET', configured_limit_bytes: 9, current_payload_bytes: 8, observed_payload_bytes: 8, candidate_id: 'candidate-1', candidate_payload_bytes: 3, forecast_payload_bytes: 11, unverified_deliveries: [], git_history_bytes: null, remote_storage_bytes: null, writes_performed: false, scope: 'Local retained payload copies' };
it('checks budget arithmetic and refuses invented remote totals or success with incomplete observations', () => {
  expect(parseMediaBudget(report)).toEqual(report);
  for (const row of [{ ...report, forecast_payload_bytes: 10 }, { ...report, status: 'WITHIN_BUDGET' }, { ...report, remote_storage_bytes: 0 }, { ...report, writes_performed: true }, { ...report, unverified_deliveries: [{ id: 'delivery-1', reason: 'Unavailable' }] }]) expect(() => parseMediaBudget(row)).toThrow();
  expect(parseMediaBudget({ ...report, status: 'UNKNOWN', current_payload_bytes: null, forecast_payload_bytes: null, unverified_deliveries: [{ id: 'delivery-1', reason: 'Unavailable' }] }).status).toBe('UNKNOWN');
});

it('binds candidate forecasts to the requested candidate identity', () => {
  expect(() => parseMediaBudget(report, 'different-candidate')).toThrow();
  expect(() => parseMediaBudget(report, null)).toThrow();
  expect(parseMediaBudget(report, 'candidate-1')).toEqual(report);
});
