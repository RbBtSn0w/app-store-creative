import { describe, expect, it, vi } from 'vitest';
import { requireConfiguredFont } from './fontReview';

describe('required configured font', () => {
  it('does not probe native system and generic fallback families', async () => {
    const load = vi.fn();
    await requireConfiguredFont(undefined, load);
    await requireConfiguredFont('-apple-system, sans-serif', load);
    await requireConfiguredFont('system-ui', load);
    expect(load).not.toHaveBeenCalled();
  });
  it('does not silently accept a missing named primary family because a fallback exists', async () => {
    const load = vi.fn().mockRejectedValue(new Error('Unavailable'));
    await expect(requireConfiguredFont('"Missing Font", sans-serif', load)).rejects.toThrow('Required font is unavailable: Missing Font');
    expect(load).toHaveBeenCalledWith('Missing Font');
  });
  it('accepts a named family only when the local face successfully loads', async () => {
    const load = vi.fn().mockResolvedValue(undefined);
    await requireConfiguredFont('"Font, Name", serif', load);
    expect(load).toHaveBeenCalledWith('Font, Name');
  });
});
