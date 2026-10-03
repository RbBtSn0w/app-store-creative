import { describe, expect, it } from 'vitest';
import { layoutIssues } from './layoutReview';

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
});
