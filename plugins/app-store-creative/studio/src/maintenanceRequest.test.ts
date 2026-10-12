import { afterEach, expect, it, vi } from 'vitest';
import { maintenanceRequest } from './maintenanceRequest';
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });
it('bounds stalled maintenance without retrying a possible write', async () => {
  vi.useFakeTimers();
  const fetch = vi.fn((_path, options) => new Promise((_resolve, reject) => {
    options?.signal?.addEventListener('abort', () => reject(new Error('aborted')));
  }));
  vi.stubGlobal('fetch', fetch);
  const promise = maintenanceRequest('/api/maintenance/quarantine', {id:'plan'});
  const outcome = promise.then(() => 'resolved', error => String(error));
  await vi.advanceTimersByTimeAsync(20001);
  expect(fetch.mock.calls[0][1]?.signal?.aborted).toBe(true);
  expect(await outcome).toContain('Check saved records');
  expect(fetch).toHaveBeenCalledTimes(1);
});

it('clears the deadline after a successful read', async () => {
  vi.useFakeTimers();
  const fetch = vi.fn().mockResolvedValue({ok:true, json:async () => ({maintenance:[]})});
  vi.stubGlobal('fetch', fetch);
  expect(await maintenanceRequest('/api/maintenance')).toEqual({maintenance:[]});
  expect(vi.getTimerCount()).toBe(0);
  await vi.advanceTimersByTimeAsync(20001);
  expect(fetch.mock.calls[0][1].signal.aborted).toBe(false);
  expect(fetch).toHaveBeenCalledTimes(1);
});
it('preserves server refusal and clears its deadline', async () => {
  vi.useFakeTimers();
  const fetch = vi.fn().mockResolvedValue({ok:false, json:async () => ({error:'Plan is stale'})});
  vi.stubGlobal('fetch', fetch);
  await expect(maintenanceRequest('/api/maintenance/quarantine', {id:'plan'})).rejects.toThrow('Plan is stale');
  expect(vi.getTimerCount()).toBe(0);
  expect(fetch).toHaveBeenCalledTimes(1);
});
