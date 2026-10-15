import { describe, it, expect } from 'vitest';
import { getTargetScalingInfo, TARGET_DIMENSIONS, TargetDevice } from './types';

describe('CardView layout scaling calculations for targets', () => {
  it('calculates proper 16:10 proportional scale for Mac targets', () => {
    const params = getTargetScalingInfo('mac_16_10');
    expect(params.baseCanvasWidth).toBe(720);
    expect(params.baseCanvasHeight).toBe(450);
    expect(params.physicalWidth).toBe(2880);
    expect(params.physicalHeight).toBe(1800);
    expect(params.exportScale).toBe(4);
  });

  it('calculates proper proportional scale for iPhone 6.9" targets', () => {
    const params = getTargetScalingInfo('iphone_6_9');
    expect(params.baseCanvasWidth).toBe(440);
    expect(params.baseCanvasHeight).toBe(956);
    expect(params.physicalWidth).toBe(1320);
    expect(params.physicalHeight).toBe(2868);
    expect(params.exportScale).toBe(3);
  });

  it('calculates exact pixel dimensions for iPad 12.9" targets without rounding drift', () => {
    const params = getTargetScalingInfo('ipad_12_9');
    expect(params.baseCanvasWidth).toBe(512);
    expect(params.baseCanvasHeight).toBe(683);
    expect(params.physicalWidth).toBe(2048);
    expect(params.physicalHeight).toBe(2732);
    expect(params.exportScale).toBe(4);
    expect(params.baseCanvasWidth * params.exportScale).toBe(params.physicalWidth);
    expect(params.baseCanvasHeight * params.exportScale).toBe(params.physicalHeight);
  });

  it('calculates exact pixel dimensions for iPhone 6.5" targets', () => {
    const params = getTargetScalingInfo('iphone_6_5');
    expect(params.baseCanvasWidth).toBe(414);
    expect(params.baseCanvasHeight).toBe(896);
    expect(params.physicalWidth).toBe(1242);
    expect(params.physicalHeight).toBe(2688);
    expect(params.exportScale).toBe(3);
    expect(params.baseCanvasWidth * params.exportScale).toBe(params.physicalWidth);
    expect(params.baseCanvasHeight * params.exportScale).toBe(params.physicalHeight);
  });

  it('guarantees exact physical dimension reproduction across all defined targets', () => {
    const targets = Object.keys(TARGET_DIMENSIONS) as TargetDevice[];
    for (const target of targets) {
      const params = getTargetScalingInfo(target);
      expect(Math.round(params.baseCanvasWidth * params.exportScale)).toBe(params.physicalWidth);
      expect(Math.round(params.baseCanvasHeight * params.exportScale)).toBe(params.physicalHeight);
    }
  });
});
