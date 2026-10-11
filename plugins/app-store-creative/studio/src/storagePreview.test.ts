import { expect, it, vi, afterEach } from 'vitest';
import { changeStorageRoot, parseStoragePreview, loadStoragePreview, storageSaveConflict } from './storagePreview';
import type { CreativeConfig } from './types';

import { specimen } from './storagePreview.fixture';
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });
it('removes a cleared override while preserving other configured roots', () => {
  const original = {storage:{workspaceRoot:'work', releaseRoot:'releases'}} as CreativeConfig;
  const result = changeStorageRoot(original, 'workspaceRoot', '');
  expect(result.storage).toEqual({releaseRoot:'releases'});
  expect(original.storage?.workspaceRoot).toBe('work');
});
it('rejects incomplete, inconsistent and mutation-bearing preview responses', () => {
  for (const value of [{}, {...specimen(), requires_relocation:undefined}, {...specimen(), writes_performed:true},
    {...specimen(), roots:{...specimen().roots, objectRoot:{configured:null, source:'derived', resolved:'/wrong'}}}]) {
    expect(() => parseStoragePreview(value)).toThrow(/incomplete|Invalid/i);
  }
});
it('keeps relocation and identity conflicts explicit', () => {
  expect(storageSaveConflict(parseStoragePreview(specimen()))).toBeNull();
  expect(storageSaveConflict(parseStoragePreview({...specimen(), requires_relocation:true}))).toContain('migration');
  expect(storageSaveConflict(parseStoragePreview({...specimen(), project_identity_conflict:true}))).toContain('identity');
});
it('sends only a draft for a read-only preview and parses its response', async () => {
  const fetch = vi.fn().mockResolvedValue({ok:true, json:async () => specimen()}); vi.stubGlobal('fetch', fetch);
  const config = {cards:[], project:{id:'product'}} as unknown as CreativeConfig;
  expect(await loadStoragePreview(config)).toEqual(specimen());
  expect(fetch.mock.calls[0][0]).toBe('/api/storage/preview');
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({config});
});
it('returns actionable failures without claiming a usable preview', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ok:false, json:async () => ({error:'Storage roots overlap'})}));
  await expect(loadStoragePreview({} as CreativeConfig)).rejects.toThrow('Storage roots overlap');
});
it('times out a stalled preview explicitly', async () => {
  vi.useFakeTimers();
  vi.stubGlobal('fetch', vi.fn((_url, options) => new Promise((_resolve, reject) => {
    options.signal.addEventListener('abort', () => reject(new Error('aborted')));
  })));
  const result = expect(loadStoragePreview({} as CreativeConfig)).rejects.toThrow('Directory preview timed out');
  await vi.advanceTimersByTimeAsync(20000); await result;
});

it('accepts protected host-local source labels', () => {
  const report = specimen();
  const value = {...report, roots:{...report.roots, workspaceRoot:{...report.roots.workspaceRoot, source:'local'}}};
  expect(parseStoragePreview(value).roots.workspaceRoot.source).toBe('local');
});
