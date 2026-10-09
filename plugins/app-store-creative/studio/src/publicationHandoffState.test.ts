import { describe, it, expect } from 'vitest';
import { parseHandoffPreview } from './publicationHandoffState';
const id = 'a'.repeat(32);
const value = { publication_id: id, plan_sha256: 'b'.repeat(64), upload_approval: 'pending', uploaded: false, remote_write: false,
  handoff: { id, target: { app_id: '123', version_id: 'version', platform: 'MAC_OS' }, assets: [{ artifact_id: 'c'.repeat(32), role: 'screenshot', sha256: 'd'.repeat(64), path: 'media/screenshot.png' }] } };
describe('bound handoff review', () => {
  it('refuses incomplete targets, wrong plan, duplicate assets and remote-write claims', () => {
    expect(parseHandoffPreview(value, id)).toEqual(value);
    expect(() => parseHandoffPreview({ ...value, handoff: { ...value.handoff, target: {} } }, id)).toThrow();
    expect(() => parseHandoffPreview(value, 'e'.repeat(32))).toThrow();
    expect(() => parseHandoffPreview({ ...value, handoff: { ...value.handoff, id: 'e'.repeat(32) } }, id)).toThrow();
    expect(() => parseHandoffPreview({ ...value, remote_write: true }, id)).toThrow();
    expect(() => parseHandoffPreview({ ...value, handoff: { ...value.handoff, assets: [value.handoff.assets[0], value.handoff.assets[0]] } }, id)).toThrow();
    expect(() => parseHandoffPreview({ ...value, upload_approval: 'unknown' }, id)).toThrow();
  });
});
