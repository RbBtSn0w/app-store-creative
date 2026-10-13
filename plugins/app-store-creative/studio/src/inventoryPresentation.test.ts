import { expect, it } from 'vitest';
import { formatInventoryBytes, inventoryStatus, parseInventory } from './inventoryPresentation';

it('keeps unavailable measurements distinct from an observed empty directory', () => {
  expect(formatInventoryBytes(null)).toBe('Not measured');
  expect(formatInventoryBytes(undefined)).toBe('Not measured');
  expect(formatInventoryBytes(0)).toBe('0 B');
  expect(formatInventoryBytes(2048)).toBe('2 KiB');
});

it('keeps terminal phases separate from damaged or unverified content', () => {
  expect(inventoryStatus('CANCELLED')).toBe('Preparation cancelled');
  expect(inventoryStatus('CHANGED')).toBe('Files differ');
  expect(inventoryStatus('IDENTITY_CONFLICT')).toBe('File or directory replaced');
  expect(inventoryStatus('PURGED')).toBe('Copies deleted');
  expect(inventoryStatus('FUTURE_STATE')).toBe('Unrecognized status: FUTURE_STATE');
});

it('rejects incomplete responses instead of displaying empty or healthy inventory', () => {
  expect(() => parseInventory({})).toThrow('Incomplete inventory response');
  expect(() => parseInventory({ objects: {}, capacity: {} })).toThrow('Incomplete inventory response');
});
