import { expect, it } from 'vitest';
import { parseMaintenanceInspection } from './maintenanceInspection';
it('does not turn recorded, incomplete or unknown results into verified execution', () => {
  const row = { id: 'abc', status: 'PASS', phase: 'purged', execution_verified: true, errors: [], remote_write: false };
  expect(parseMaintenanceInspection(row, 'abc')).toEqual(row);
  for (const changed of [{ ...row, id: 'def' }, { ...row, remote_write: true }, { ...row, status: 'UNKNOWN' }, { ...row, status: 'INCOMPLETE' }, { ...row, execution_verified: false }, { ...row, errors: [null] }]) expect(() => parseMaintenanceInspection(changed, 'abc')).toThrow();
  expect(parseMaintenanceInspection({ ...row, status: 'UNKNOWN', execution_verified: false }, 'abc').execution_verified).toBe(false);
});
