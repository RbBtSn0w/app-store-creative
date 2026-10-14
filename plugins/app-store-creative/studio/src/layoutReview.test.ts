import { describe, expect, it } from 'vitest';
import { layoutIssues, classifyPose } from './layoutReview';

const bounds = { left: 0, top: 0, right: 400, bottom: 870 };
const copy = { left: 30, top: 40, right: 370, bottom: 120 };

describe('preview and export layout review', () => {
  it('accepts wrapped text within its canvas and clear device bounds', () => {
    expect(layoutIssues(bounds, [copy], copy, { left: 30, top: 150, right: 370, bottom: 900 })).toEqual([]);
  });
  it('rejects text extending below the canvas', () => {
    expect(layoutIssues(bounds, [{ ...copy, bottom: 900 }])).toContain('Text is clipped; shorten the copy or select another layout');
  });
  it('detects a transformed device overlapping text despite a clear reserved region', () => {
    expect(layoutIssues(bounds, [copy], copy, { left: 30, top: 110, right: 370, bottom: 830 })).toContain('Copy overlaps the device; shorten the copy or select another layout');
  });
  it('accepts side-by-side copy and device regardless of vertical alignment', () => {
    expect(layoutIssues(bounds, [copy], { ...copy, right: 150 }, { left: 160, top: 30, right: 380, bottom: 320 })).toEqual([]);
  });
  it('ignores subpixel contact / slight 3D bounding box projection under 4px', () => {
    expect(layoutIssues(bounds, [copy], copy, { left: 30, top: 118, right: 370, bottom: 830 })).toEqual([]);
  });
});

describe('classifyPose', () => {
  it('identifies hero 3D pose preset', () => {
    expect(classifyPose({ rotateX: 4, rotateY: 0, rotate: 0, scale: 1.05, y: 15 })).toBe('hero');
  });

  it('identifies inward gaze pose preset with either positive or negative yaw', () => {
    expect(classifyPose({ rotateX: 4, rotateY: 8, rotate: -2, scale: 1.02 })).toBe('gaze');
    expect(classifyPose({ rotateX: 4, rotateY: -8, rotate: 2, scale: 1.02 })).toBe('gaze');
  });

  it('distinguishes grounded pose from flat pose based on scale', () => {
    expect(classifyPose({ rotateX: 0, rotateY: 0, rotate: 0, scale: 0.95 })).toBe('grounded');
    expect(classifyPose({ rotateX: 0, rotateY: 0, rotate: 0, scale: 1.0 })).toBe('flat');
    expect(classifyPose()).toBe('flat');
  });

  it('classifies unaligned arbitrary transforms as custom', () => {
    expect(classifyPose({ rotateX: 12, rotateY: 5, scale: 1.15 })).toBe('custom');
  });
});
