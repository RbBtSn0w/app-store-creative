export interface ProjectInfo {
  id: string;
  name: string;
  bundleId: string;
  defaultLocale?: string;
  locales?: string[];
}

export type TargetDevice =
  | 'iphone_6_9'
  | 'iphone_6_7'
  | 'iphone_6_5'
  | 'iphone_5_5'
  | 'ipad_13'
  | 'ipad_12_9'
  | 'mac_16_10'
  | 'watch_ultra'
  | 'google_play_phone'
  | 'google_play_tablet_7'
  | 'google_play_tablet_10'
  | 'google_play_feature_graphic';

export interface DeviceDimensions {
  width: number;
  height: number;
  displayName: string;
  aspectRatio: string;
}

export const TARGET_DIMENSIONS: Record<TargetDevice, DeviceDimensions> = {
  iphone_6_9: { width: 1320, height: 2868, displayName: 'iPhone 16 Pro Max (6.9")', aspectRatio: '1320/2868' },
  iphone_6_7: { width: 1290, height: 2796, displayName: 'iPhone 15 Pro Max (6.7")', aspectRatio: '1290/2796' },
  iphone_6_5: { width: 1242, height: 2688, displayName: 'iPhone 11 Pro Max (6.5")', aspectRatio: '1242/2688' },
  iphone_5_5: { width: 1242, height: 2208, displayName: 'iPhone 8 Plus (5.5")', aspectRatio: '1242/2208' },
  ipad_13: { width: 2064, height: 2752, displayName: 'iPad Pro 13" M4', aspectRatio: '2064/2752' },
  ipad_12_9: { width: 2048, height: 2732, displayName: 'iPad Pro 12.9"', aspectRatio: '2048/2732' },
  mac_16_10: { width: 2880, height: 1800, displayName: 'MacBook Pro 16:10', aspectRatio: '16/10' },
  watch_ultra: { width: 410, height: 502, displayName: 'Apple Watch Ultra', aspectRatio: '410/502' },
  google_play_phone: { width: 1080, height: 2400, displayName: 'Google Play Phone (9:20)', aspectRatio: '9/20' },
  google_play_tablet_7: { width: 1200, height: 1920, displayName: 'Google Play 7" Tablet', aspectRatio: '10/16' },
  google_play_tablet_10: { width: 1600, height: 2560, displayName: 'Google Play 10" Tablet', aspectRatio: '10/16' },
  google_play_feature_graphic: { width: 1024, height: 500, displayName: 'Google Play Feature Graphic', aspectRatio: '1024/500' },
};

export interface TargetScalingInfo {
  baseCanvasWidth: number;
  baseCanvasHeight: number;
  exportScale: number;
  physicalWidth: number;
  physicalHeight: number;
  isMac: boolean;
  isTablet: boolean;
  isFeatureGraphic: boolean;
}

export function getTargetScalingInfo(target: TargetDevice): TargetScalingInfo {
  const isFeatureGraphic = target === 'google_play_feature_graphic';
  const isMac = target.startsWith('mac_');
  const isTablet = target.startsWith('ipad_') || target.startsWith('google_play_tablet_');
  const baseCanvasWidth = isFeatureGraphic ? 600 : isMac ? 720 : isTablet ? 480 : 400;
  const targetDim = TARGET_DIMENSIONS[target] || TARGET_DIMENSIONS.iphone_6_9;
  const baseCanvasHeight = Math.round(baseCanvasWidth * (targetDim.height / targetDim.width));
  const exportScale = targetDim.width / baseCanvasWidth;

  return {
    baseCanvasWidth,
    baseCanvasHeight,
    exportScale,
    physicalWidth: targetDim.width,
    physicalHeight: targetDim.height,
    isMac,
    isTablet,
    isFeatureGraphic,
  };
}

export interface BackgroundConfig {
  type: 'solid' | 'gradient' | 'mesh' | 'image';
  colors?: string[];
  angle?: number;
  imageUrl?: string;
}

export interface ThemeConfig {
  stylePreset?: string;
  background: BackgroundConfig;
  fontFamily?: string;
  headlineColor?: string;
  subheadlineColor?: string;
  bezelStyle?: 'natural' | 'titanium_black' | 'titanium_natural' | 'silver' | 'midnight' | 'flat';
  shadow?: 'soft' | 'dramatic' | 'subtle' | 'none';
}

export interface CardOffset {
  x?: number;
  y?: number;
  scale?: number;
  rotate?: number;
  rotateX?: number;
  rotateY?: number;
}

export interface LocalizedCard {
  headline?: string;
  subheadline?: string;
  screenshot?: string;
  inheritDefault?: boolean;
}

export interface CardVariant {
  screenshot?: string;
  layout?: CardConfig['layout'];
  deviceOffset?: CardOffset;
  localizations?: Record<string, LocalizedCard>;
}

export interface CardConfig {
  id: string;
  headline: string;
  subheadline?: string;
  screenshot?: string;
  layout?:
    | 'mac_native_hero'
    | 'mac_native_left'
    | 'mac_native_right'
    | 'phone_bottom'
    | 'phone_center'
    | 'phone_tilt_left'
    | 'phone_tilt_right'
    | 'phone_bleed'
    | 'split_dual'
    | 'pure_text'
    | 'phone_floating_isometric'
    | 'phone_perspective_hero'
    | 'split_dual_perspective'
    | 'feature_graphic_banner';
  deviceOffset?: CardOffset;
  customBackground?: BackgroundConfig;
  variants?: Partial<Record<TargetDevice, CardVariant>>;
}

export type ArchivePolicy =
  | { schema_version: 1; mediaMode: 'git' | 'lfs'; backend?: never }
  | { schema_version: 1; mediaMode: 'external'; backend: string };

export interface CreativeConfig {
  archivePolicy?: ArchivePolicy;
  storage?: { workspaceRoot?: string; objectRoot?: string; releaseRoot?: string; publicationRoot?: string };
  project: ProjectInfo;
  targets: TargetDevice[];
  theme: ThemeConfig;
  connectedTrack?: boolean;
  cards: CardConfig[];
  previewVideo?: {
    locales?: string[];
    enabled: boolean;
    source?: string;
    fps?: number;
    duration?: number;
    orientation?: 'portrait' | 'landscape';
    width?: number;
    height?: number;
    audio?: {
      required?: boolean;
      addSilentTrackIfMissing?: boolean;
    };
  };
  localizations?: Record<string, Record<string, LocalizedCard>>;
  studio?: { requireExportEvidence?: boolean };
}
