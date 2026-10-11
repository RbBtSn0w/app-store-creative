import { describe, it, expect } from 'vitest';
import { parseRelocationPlan } from './relocationState';
const binding = { workspace: '/test/work', objects: '/test/media', releases: '/test/releases', publications: '/test/publications' };
const plan = { id: 'a'.repeat(32), operation: 'relocation-plan', from: binding, to: binding, files: [{ root: 'objects', path: 'aa/object', sha256: 'b'.repeat(64), size_bytes: 10 }], logical_bytes: 10 };
describe('relocation plan review', () => {
  it('accepts the complete plan and rejects misleading totals or incomplete scope', () => {
    expect(parseRelocationPlan(plan)).toEqual(plan);
    const reverse = { ...plan, operation: 'reverse-relocation-plan' };
    expect(parseRelocationPlan(reverse)).toEqual(reverse);
    expect(() => parseRelocationPlan({ ...plan, logical_bytes: 11 })).toThrow();
    expect(() => parseRelocationPlan({ ...plan, from: { workspace: '/test/work' } })).toThrow();
    expect(() => parseRelocationPlan({ ...plan, files: [null] })).toThrow();
    expect(() => parseRelocationPlan({ ...plan, files: [{ ...plan.files[0], path: '../outside' }] })).toThrow();
    expect(() => parseRelocationPlan({ ...plan, files: [plan.files[0], plan.files[0]], logical_bytes: 20 })).toThrow();
    expect(() => parseRelocationPlan({ ...plan, files: [{ ...plan.files[0], sha256: 'bad' }] })).toThrow();
  });
});
