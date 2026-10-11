import { describe, expect, it } from 'vitest';
import { parseRunPage, parseRunDetail } from './RunHistory';

describe('production history response validation', () => {
  it('preserves complete production records and nullable outcomes', () => {
    const page = { runs: [{ id: 'run', created_at: '2026-10-10T00:00:00Z',
      target: { version: '1.5', platform: 'MAC_OS' } }], next_cursor: 'cursor' };
    const detail = { attempts: [{ id: 'attempt', stage: 'capture', outcome: null },
      { id: 'finished', stage: 'export', outcome: { status: 'failed', reason: 'Interrupted' } }],
      artifacts: [{ id: 'asset', role: 'screenshot', partial: true,
        candidate_eligible: false, eligibility_errors: ['Partial output'] }] };
    expect(parseRunPage(page)).toEqual(page);
    expect(parseRunDetail(detail)).toEqual(detail);
  });
  it('rejects malformed pages before rendering', () => {
    for (const value of [null, {}, { runs: [null], next_cursor: null },
      { runs: [{ id: 'run', created_at: 'now', target: null }], next_cursor: null }]) {
      expect(() => parseRunPage(value)).toThrow();
    }
    expect(parseRunPage({ runs: [], next_cursor: null }).runs).toEqual([]);
  });
  it('rejects malformed details and ambiguous eligibility', () => {
    for (const value of [null, {}, { attempts: [null], artifacts: [] },
      { attempts: [], artifacts: [{ id: 'asset', role: 'screenshot', partial: false,
        candidate_eligible: 'false', eligibility_errors: [] }] }]) {
      expect(() => parseRunDetail(value)).toThrow();
    }
    expect(parseRunDetail({ attempts: [], artifacts: [] }).artifacts).toEqual([]);
  });
});
