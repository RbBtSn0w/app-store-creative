import { afterEach, expect, it, vi } from 'vitest';
import { waitForExport } from './ExportView';

afterEach(() => vi.useRealTimers());
it('keeps timeout terminal when rendering becomes ready later', async () => {
  vi.useFakeTimers();
  let finish!: () => void;
  const ready = vi.fn();
  const failed = vi.fn();
  const result = waitForExport(new Promise<void>(resolve => { finish = resolve; }))
    .then(ready, failed);
  await vi.advanceTimersByTimeAsync(6001);
  await result;
  expect(failed).toHaveBeenCalledOnce();
  expect(failed.mock.calls[0][0].message).toContain('did not become ready');
  finish();
  await Promise.resolve();
  expect(ready).not.toHaveBeenCalled();
  expect(vi.getTimerCount()).toBe(0);
});
it('clears the deadline on success and preserves rendering errors', async () => {
  vi.useFakeTimers();
  await waitForExport(Promise.resolve());
  const error = new Error('Capture could not be decoded');
  await expect(waitForExport(Promise.reject(error))).rejects.toBe(error);
  expect(vi.getTimerCount()).toBe(0);
});
