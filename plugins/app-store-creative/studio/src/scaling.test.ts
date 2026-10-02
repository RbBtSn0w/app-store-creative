import { describe, it, expect } from 'vitest';
import { getTargetScalingInfo } from './types';

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
    expect(params.baseCanvasWidth).toBe(400);
    expect(params.physicalWidth).toBe(1320);
    expect(params.physicalHeight).toBe(2868);
    expect(params.exportScale).toBe(3.3);
  });

  it('calculates proper proportional scale for iPad targets', () => {
    const params = getTargetScalingInfo('ipad_13');
    expect(params.baseCanvasWidth).toBe(480);
    expect(params.physicalWidth).toBe(2064);
    expect(params.physicalHeight).toBe(2752);
    expect(params.exportScale).toBeCloseTo(4.3, 1);
  });

  it('calculates proper proportional scale for Google Play feature graphics', () => {
    const params = getTargetScalingInfo('google_play_feature_graphic');
    expect(params.baseCanvasWidth).toBe(600);
    expect(params.physicalWidth).toBe(1024);
    expect(params.physicalHeight).toBe(500);
    expect(params.exportScale).toBeCloseTo(1.707, 2);
  });
});
