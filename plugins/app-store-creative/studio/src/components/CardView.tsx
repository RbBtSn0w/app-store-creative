import React from 'react';
import { CardConfig, TargetDevice, ThemeConfig, getTargetScalingInfo } from '../types';
import { DeviceFrame } from './DeviceFrame';
import { STYLE_PRESETS, StylePresetId } from '../stylePresets';

interface CardViewProps {
  card: CardConfig;
  index: number;
  totalCards?: number;
  target: TargetDevice;
  theme: ThemeConfig;
  locale?: string;
  localizedText?: { headline: string; subheadline?: string };
  isExport?: boolean;
  connected?: boolean;
  onUpdateText?: (field: 'headline' | 'subheadline', value: string) => void;
}

export const CardView: React.FC<CardViewProps> = ({
  card,
  index,
  target,
  theme,
  localizedText,
  isExport = false,
  onUpdateText,
}) => {
  const headline = localizedText?.headline || card.headline;
  const subheadline = localizedText?.subheadline || card.subheadline;
  const layout = card.layout || 'phone_bottom';

  // Resolve theme with style preset if specified
  const preset = theme.stylePreset && (theme.stylePreset in STYLE_PRESETS)
    ? STYLE_PRESETS[theme.stylePreset as StylePresetId]
    : undefined;

  const resolvedTheme: ThemeConfig = {
    ...theme,
    headlineColor: preset?.theme.headlineColor || theme.headlineColor || '#FFFFFF',
    subheadlineColor: preset?.theme.subheadlineColor || theme.subheadlineColor || 'rgba(255, 255, 255, 0.75)',
    bezelStyle: preset?.theme.bezelStyle || theme.bezelStyle || 'natural',
    shadow: preset?.theme.shadow || theme.shadow || 'dramatic',
    background: card.customBackground || (preset?.theme.background || theme.background),
  };

  // Compute background style
  const bg = card.customBackground || resolvedTheme.background;
  const getBackgroundStyle = () => {
    if (bg.type === 'solid' && bg.colors?.[0]) {
      return { backgroundColor: bg.colors[0] };
    }
    if (bg.type === 'gradient' && bg.colors && bg.colors.length >= 2) {
      const angle = bg.angle ?? 135;
      return {
        backgroundImage: `linear-gradient(${angle}deg, ${bg.colors.join(', ')})`,
      };
    }
    return {
      backgroundImage: 'linear-gradient(135deg, #0A0E1A 0%, #1E1B4B 50%, #311042 100%)',
    };
  };

  const isFeatureGraphic = target === 'google_play_feature_graphic' || layout === 'feature_graphic_banner';

  const getLayoutClasses = () => {
    if (isFeatureGraphic) {
      return 'flex-row items-center justify-between px-10 py-6';
    }
    switch (layout) {
      case 'phone_center':
        return 'justify-center items-center py-8';
      case 'phone_bleed':
        return 'justify-between items-center pb-0';
      case 'phone_floating_isometric':
      case 'phone_perspective_hero':
      case 'split_dual_perspective':
      case 'phone_tilt_left':
      case 'phone_tilt_right':
      case 'phone_bottom':
      default:
        return 'justify-between items-center';
    }
  };

  // Calculate layout-specific default 3D offsets if not explicitly set
  const computedOffset = {
    x: card.deviceOffset?.x ?? 0,
    y: card.deviceOffset?.y ?? (target.startsWith('mac_') ? 0 : layout === 'phone_floating_isometric' ? 40 : 25),
    scale: card.deviceOffset?.scale ?? (layout === 'phone_perspective_hero' ? 1.08 : 1),
    rotate: card.deviceOffset?.rotate ?? (layout === 'phone_floating_isometric' ? -6 : 0),
    rotateX: card.deviceOffset?.rotateX ?? (layout === 'phone_floating_isometric' ? 14 : layout === 'phone_perspective_hero' ? 18 : 0),
    rotateY: card.deviceOffset?.rotateY ?? (layout === 'phone_floating_isometric' ? -12 : 0),
  };

  // Compute virtual base canvas dimensions and physical export scale factor
  const {
    baseCanvasWidth,
    baseCanvasHeight,
    exportScale,
    physicalWidth,
    physicalHeight,
    isMac,
  } = getTargetScalingInfo(target);

  const cardContent = (
    <div
      data-card-id={card.id}
      data-card-index={index}
      className={`relative flex ${isFeatureGraphic ? 'flex-row items-center justify-between p-8' : 'flex-col'} overflow-hidden text-center select-none shadow-2xl transition-all duration-300 ${
        isExport ? '' : 'rounded-[32px] ring-1 ring-white/10'
      } ${getLayoutClasses()}`}
      style={{
        width: `${baseCanvasWidth}px`,
        height: `${baseCanvasHeight}px`,
        ...getBackgroundStyle(),
      }}
    >
      {/* Decorative ambient glow or mesh elements */}
      <div className="pointer-events-none absolute -top-24 -left-24 w-72 h-72 bg-indigo-500/20 rounded-full blur-3xl" />
      <div className="pointer-events-none absolute -bottom-24 -right-24 w-80 h-80 bg-purple-500/20 rounded-full blur-3xl" />

      {/* Top Marketing Copy Section */}
      <div className={`relative z-20 ${isFeatureGraphic ? 'text-left max-w-[50%] px-4' : isMac ? 'pt-8 px-8 pb-3 max-w-[85%] mx-auto flex flex-col items-center' : 'pt-12 px-6 pb-4 max-w-[90%] mx-auto flex flex-col items-center'}`}>
        <h2
          contentEditable={!isExport && !!onUpdateText}
          suppressContentEditableWarning
          onBlur={(e) => onUpdateText?.('headline', e.currentTarget.textContent || '')}
          className="text-2xl md:text-3xl font-extrabold tracking-tight leading-tight mb-2 drop-shadow-md outline-none focus:ring-1 focus:ring-blue-400 rounded px-1"
          style={{
            color: resolvedTheme.headlineColor || '#FFFFFF',
            fontFamily: resolvedTheme.fontFamily,
          }}
        >
          {headline}
        </h2>
        {subheadline && (
          <p
            contentEditable={!isExport && !!onUpdateText}
            suppressContentEditableWarning
            onBlur={(e) => onUpdateText?.('subheadline', e.currentTarget.textContent || '')}
            className={`text-sm font-medium tracking-normal leading-snug drop-shadow-sm outline-none focus:ring-1 focus:ring-blue-400 rounded px-1 ${
              isFeatureGraphic ? 'max-w-[320px]' : isMac ? 'max-w-[420px]' : 'max-w-[280px]'
            }`}
            style={{
              color: resolvedTheme.subheadlineColor || 'rgba(255, 255, 255, 0.75)',
              fontFamily: resolvedTheme.fontFamily,
            }}
          >
            {subheadline}
          </p>
        )}
      </div>

      {/* Device Frame Display Area */}
      <div className={`relative z-10 ${isFeatureGraphic ? 'flex-1 h-full flex items-center justify-center' : isMac ? 'flex-1 w-full min-h-0 flex items-center justify-center pb-4' : 'flex-1 w-full flex items-end justify-center overflow-visible pb-0'}`}>
        <DeviceFrame
          screenshot={card.screenshot}
          offset={computedOffset}
          theme={resolvedTheme}
          target={target}
          className={
            isMac
              ? ''
              : isFeatureGraphic
              ? 'scale-75 -translate-y-4'
              : layout === 'phone_bleed'
              ? 'scale-110 translate-y-12'
              : 'translate-y-6'
          }
        />
      </div>

      {/* Visual metadata badge */}
      {!isExport && (
        <div className="absolute bottom-2 left-3 z-30 pointer-events-none">
          <span className="text-[10px] uppercase font-mono tracking-wider px-2 py-0.5 rounded-full bg-black/40 text-white/60 backdrop-blur-sm border border-white/5">
            {card.id}
          </span>
        </div>
      )}
    </div>
  );

  if (isExport) {
    return (
      <div
        className="w-full h-full overflow-hidden flex items-center justify-center"
        style={{
          width: `${physicalWidth}px`,
          height: `${physicalHeight}px`,
        }}
      >
        <div
          style={{
            width: `${baseCanvasWidth}px`,
            height: `${baseCanvasHeight}px`,
            transform: `scale(${exportScale})`,
            transformOrigin: 'center center',
          }}
        >
          {cardContent}
        </div>
      </div>
    );
  }

  return cardContent;
};
