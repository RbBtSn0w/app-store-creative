import { describe, expect, it } from 'vitest';
import { deliveryVerdict } from './deliveryStatus';

describe('delivery verification presentation', () => {
  it('requires every local proof before displaying verified', () => {
    expect(deliveryVerdict({ local_status: 'PASS', package_verified: true, recipe_verified: true, provenance_verified: true })).toBe('Local archive verified');
    expect(deliveryVerdict({ local_status: 'PASS', package_verified: true, recipe_verified: true, provenance_verified: false })).toBe('Local verification incomplete');
  });
  it('reports failed or incomplete status without inferring completion', () => {
    expect(deliveryVerdict({ local_status: 'FAIL' })).toBe('Local archive failed');
    expect(deliveryVerdict({ local_status: 'UNKNOWN' })).toBe('Local verification incomplete');
  });
});
