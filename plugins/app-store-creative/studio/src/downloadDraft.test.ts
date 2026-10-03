import { afterEach, expect, it, vi } from 'vitest';
import { downloadDraft } from './downloadDraft';

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

it('keeps the draft URL live until the download click has been dispatched', () => {
  vi.useFakeTimers();
  const revoke = vi.fn();
  const link = { href: '', download: '', click: vi.fn(), remove: vi.fn() };
  const append = vi.fn();
  vi.stubGlobal('document', { createElement: () => link, body: { appendChild: append } });
  vi.stubGlobal('URL', { createObjectURL: () => 'blob:draft', revokeObjectURL: revoke });
  downloadDraft({ cards: [] });
  expect(revoke).not.toHaveBeenCalled();
  expect(append).toHaveBeenCalledWith(link);
  expect(link.download).toBe('creative-draft.json');
  expect(link.click).toHaveBeenCalledOnce();
  vi.runAllTimers();
  expect(revoke).toHaveBeenCalledWith('blob:draft');
  expect(link.remove).toHaveBeenCalledOnce();
});
