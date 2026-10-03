import { describe, expect, it } from 'vitest';
import { releaseState } from './releaseState';

const base = { hasCards: true, dirty: false, saving: false, busy: false, exporting: false,
  verified: false, error: false, inputsChecked: true, inputsMissing: false, layoutErrors: false };

describe('release state truthfulness', () => {
  it('distinguishes ready inputs from an incomplete output matrix', () => {
    expect(releaseState(base)).toBe('Ready to export');
  });
  it('never reports failed operations or known layout problems as ready', () => {
    expect(releaseState({ ...base, error: true })).toBe('Needs attention');
    expect(releaseState({ ...base, layoutErrors: true })).toBe('Needs attention');
  });
  it('requires an input check before claiming readiness', () => {
    expect(releaseState({ ...base, inputsChecked: false })).toBe('Needs input');
    expect(releaseState({ ...base, inputsMissing: true })).toBe('Needs input');
  });
  it('prioritizes current edits and work over prior verification', () => {
    expect(releaseState({ ...base, verified: true, dirty: true })).toBe('Unsaved changes');
    expect(releaseState({ ...base, verified: true, busy: true, exporting: true })).toBe('Exporting');
    expect(releaseState({ ...base, verified: true })).toBe('Verified locally');
  });
  it('keeps legacy file checks distinct from a reviewed render release', () => {
    expect(releaseState({ ...base, legacyChecked: true })).toBe('Files checked');
  });

});
