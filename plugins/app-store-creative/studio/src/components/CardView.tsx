import React from 'react';
import { CardConfig, TargetDevice, ThemeConfig } from '../types';
import { DeviceFrame } from './DeviceFrame';

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
}

export const CardView: React.FC<CardViewProps> = ({
  card,
  index,
  target,
  theme,
  localizedText,
  isExport = false,
}) => {
  const headline = localizedText?.headline || card.headline;
  const subheadline = localizedText?.subheadline || card.subheadline;
  const layout = card.layout || 'phone_bottom';

  // Compute background
  const bg = card.customBackground || theme.background;
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

  const getLayoutClasses = () => {
    switch (layout) {
      case 'phone_center':
        return 'justify-center items-center py-8';
      case 'phone_bleed':
        return 'justify-between items-center pb-0';
      case 'phone_tilt_left':
      case 'phone_tilt_right':
      case 'phone_bottom':
      default:
        return 'justify-between items-center';
    }
  };

  const previewWidth = 400;
  const previewHeight = 869;

  return (
    <div
      data-card-id={card.id}
      data-card-index={index}
      className={`relative flex flex-col overflow-hidden text-center select-none shadow-2xl transition-all duration-300 ${
        isExport ? 'w-full h-full' : 'rounded-[32px] ring-1 ring-white/10'
      } ${getLayoutClasses()}`}
      style={{
        width: isExport ? '100%' : `${previewWidth}px`,
        height: isExport ? '100%' : `${previewHeight}px`,
        ...getBackgroundStyle(),
      }}
    >
      {/* Decorative ambient glow or mesh elements */}
      <div className="pointer-events-none absolute -top-24 -left-24 w-72 h-72 bg-indigo-500/20 rounded-full blur-3xl" />
      <div className="pointer-events-none absolute -bottom-24 -right-24 w-80 h-80 bg-purple-500/20 rounded-full blur-3xl" />

      {/* Top Marketing Copy Section */}
      <div className="relative z-20 pt-12 px-6 pb-4 max-w-[90%] mx-auto flex flex-col items-center">
        <h2
          className="text-2xl md:text-3xl font-extrabold tracking-tight leading-tight mb-2 drop-shadow-md"
          style={{
            color: theme.headlineColor || '#FFFFFF',
            fontFamily: theme.fontFamily,
          }}
        >
          {headline}
        </h2>
        {subheadline && (
          <p
            className="text-sm font-medium tracking-normal leading-snug drop-shadow-sm max-w-[280px]"
            style={{
              color: theme.subheadlineColor || 'rgba(255, 255, 255, 0.75)',
              fontFamily: theme.fontFamily,
            }}
          >
            {subheadline}
          </p>
        )}
      </div>

      {/* Device Frame Display Area */}
      <div className="relative z-10 flex-1 w-full flex items-end justify-center overflow-visible pb-0">
        <DeviceFrame
          screenshot={card.screenshot}
          offset={card.deviceOffset}
          theme={theme}
          target={target}
          className={layout === 'phone_bleed' ? 'scale-110 translate-y-12' : 'translate-y-6'}
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
};
