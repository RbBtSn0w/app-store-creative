import { describe, it, expect } from 'vitest';
import { TARGET_DIMENSIONS, TargetDevice } from './types';

describe('CardView layout scaling calculations for targets', () => {
  const getScalingParameters = (target: TargetDevice) => {
    const isFeatureGraphic = target === 'google_play_feature_graphic';
    const isMac = target.startsWith('mac_');
    const isTablet = target.startsWith('ipad_') || target.startsWith('google_play_tablet_');
    const baseCanvasWidth = isFeatureGraphic ? 600 : isMac ? 720 : isTablet ? 480 : 400;
    const targetDim = TARGET_DIMENSIONS[target] || TARGET_DIMENSIONS.iphone_6_9;
    const baseCanvasHeight = Math.round(baseCanvasWidth * (targetDim.height / targetDim.width));
    const exportScale = targetDim.width / baseCanvasWidth;
    return { baseCanvasWidth, baseCanvasHeight, exportScale, physicalWidth: targetDim.width, physicalHeight: targetDim.height };
  };

  it('calculates proper 16:10 proportional scale for Mac targets', () => {
    const params = getScalingParameters('mac_16_10');
    expect(params.baseCanvasWidth).toBe(720);
    expect(params.baseCanvasHeight).toBe(450);
    expect(params.physicalWidth).toBe(2880);
    expect(params.physicalHeight).toBe(1800);
    expect(params.exportScale).toBe(4);
  });

  it('calculates proper proportional scale for iPhone 6.9" targets', () => {
    const params = getScalingParameters('iphone_6_9');
    expect(params.baseCanvasWidth).toBe(400);
    expect(params.physicalWidth).toBe(1320);
    expect(params.physicalHeight).toBe(2868);
    expect(params.exportScale).toBe(3.3);
  });

  it('calculates proper proportional scale for iPad targets', () => {
    const params = getScalingParameters('ipad_13');
    expect(params.baseCanvasWidth).toBe(480);
    expect(params.physicalWidth).toBe(2064);
    expect(params.physicalHeight).toBe(2752);
    expect(params.exportScale).toBeCloseTo(4.3, 1);
  });

  it('calculates proper proportional scale for Google Play feature graphics', () => {
    const params = getScalingParameters('google_play_feature_graphic');
    expect(params.baseCanvasWidth).toBe(600);
    expect(params.physicalWidth).toBe(1024);
    expect(params.physicalHeight).toBe(500);
    expect(params.exportScale).toBeCloseTo(1.707, 2);
  });
});
