import { expect, it } from 'vitest';
import { parseRelocatedObjects } from './relocatedObjects';
it('binds verification to exact relocation and a nonempty checked scope', () => {
  const row = { id: 'abc', status: 'PASS', object_integrity_verified: true, checked_files: 1, errors: [], scope: 'Copied objects', remote_write: false };
  expect(parseRelocatedObjects(row, 'abc')).toEqual(row);
  for (const changed of [{ ...row, id: 'def' }, { ...row, checked_files: 0 }, { ...row, checked_files: -1 }, { ...row, status: 'UNKNOWN' }, { ...row, object_integrity_verified: false }, { ...row, remote_write: true }, { ...row, errors: [null] }]) expect(() => parseRelocatedObjects(changed, 'abc')).toThrow();
  expect(parseRelocatedObjects({ ...row, status: 'UNKNOWN', object_integrity_verified: false, checked_files: 0 }, 'abc').object_integrity_verified).toBe(false);
});
