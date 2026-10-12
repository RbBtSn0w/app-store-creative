import { afterEach, expect, it, vi } from 'vitest';
import { readHistory } from './historyRequest';
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

it('aborts a stalled history request and returns a recoverable error', async () => {
  vi.useFakeTimers();
  vi.stubGlobal('fetch', vi.fn((_path, options) => new Promise((_resolve, reject) => {
    options.signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
  })));
  const result = expect(readHistory('/api/runs')).rejects.toThrow('History request timed out. Try again.');
  await vi.advanceTimersByTimeAsync(20000);
  await result;
  expect(vi.getTimerCount()).toBe(0);
});

it('preserves a server error and clears the timeout', async () => {
  vi.useFakeTimers();
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok:false, json:async () => ({error:'Unknown run'}) })));
  await expect(readHistory('/api/runs/missing')).rejects.toThrow('Unknown run');
  expect(vi.getTimerCount()).toBe(0);
});

it('returns successful data without leaving a timer', async () => {
  vi.useFakeTimers();
  vi.stubGlobal('fetch', vi.fn(async () => ({ok:true, json:async () => ({runs:[],next_cursor:null})})));
  await expect(readHistory('/api/runs')).resolves.toEqual({runs:[],next_cursor:null});
  expect(vi.getTimerCount()).toBe(0);
});

it('identifies a timed out inventory check instead of calling it history', async () => {
  vi.useFakeTimers();
  vi.stubGlobal('fetch', vi.fn((_path, options) => new Promise((_resolve, reject) => {
    options.signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
  })));
  const result = readHistory('/api/inventory', 'asset inventory').then(() => null, error => error);
  await vi.advanceTimersByTimeAsync(20000);
  const failure = await result;
  expect(failure).toBeInstanceOf(Error);
  expect(failure.message).toBe('Asset inventory request timed out. Try again.');
  expect(vi.getTimerCount()).toBe(0);
});
