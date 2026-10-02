import React from 'react';
import { CardOffset, TargetDevice, ThemeConfig } from '../types';

interface DeviceFrameProps {
  screenshot?: string;
  offset?: CardOffset;
  theme?: ThemeConfig;
  target?: TargetDevice;
  className?: string;
}

export const DeviceFrame: React.FC<DeviceFrameProps> = ({
  screenshot,
  offset = {},
  theme,
  target = 'iphone_6_9',
  className = '',
}) => {
  const { x = 0, y = 0, scale = 1, rotate = 0, rotateX = 0, rotateY = 0 } = offset;
  const shadowStyle = theme?.shadow || 'dramatic';
  const bezelStyle = theme?.bezelStyle || 'natural';

  const transform3d = `perspective(1200px) translate3d(${x}px, ${y}px, 0) scale(${scale}) rotate(${rotate}deg) rotateX(${rotateX}deg) rotateY(${rotateY}deg)`;

  // Shadow classes
  const getShadow = () => {
    switch (shadowStyle) {
      case 'dramatic':
        return 'drop-shadow-[0_35px_60px_rgba(0,0,0,0.65)] drop-shadow-[0_15px_25px_rgba(0,0,0,0.4)]';
      case 'soft':
        return 'drop-shadow-[0_20px_40px_rgba(0,0,0,0.35)]';
      case 'subtle':
        return 'drop-shadow-[0_10px_20px_rgba(0,0,0,0.2)]';
      case 'none':
      default:
        return '';
    }
  };

  // Bezel border styles
  const getBezelGradient = () => {
    switch (bezelStyle) {
      case 'titanium_black':
        return 'bg-gradient-to-b from-[#3A393E] via-[#1E1E22] to-[#2B2A2E] ring-1 ring-[#525157]/40';
      case 'titanium_natural':
        return 'bg-gradient-to-b from-[#8C867E] via-[#635D56] to-[#7A746C] ring-1 ring-[#A59F97]/50';
      case 'silver':
        return 'bg-gradient-to-b from-[#E2E2E6] via-[#B9B9C0] to-[#D5D5DB] ring-1 ring-white/60';
      case 'midnight':
        return 'bg-gradient-to-b from-[#1C2333] via-[#0E131F] to-[#161D2B] ring-1 ring-[#323D57]/40';
      case 'flat':
        return 'bg-[#1A1A1A] ring-1 ring-black';
      case 'natural':
      default:
        return 'bg-gradient-to-b from-[#4A4A4E] via-[#2A2A2E] to-[#3A3A3E] ring-1 ring-white/20';
    }
  };

  const isTablet = target.startsWith('ipad_') || target.startsWith('google_play_tablet_');
  const isMac = target.startsWith('mac_');
  const isAndroidPhone = target === 'google_play_phone';

  // RENDER MAC FRAME
  if (isMac) {
    return (
      <div
        className={`relative transition-transform duration-200 select-none ${getShadow()} ${className}`}
        style={{
          transform: transform3d,
          transformOrigin: 'center center',
          transformStyle: 'preserve-3d',
        }}
      >
        <div className={`relative w-[480px] h-[260px] rounded-[16px] p-[8px] ${getBezelGradient()}`}>
          <div className="relative w-full h-full bg-[#121214] rounded-[10px] overflow-hidden shadow-inner flex flex-col">
            {/* Preserve the captured window's native chrome and complete content. */}
            {screenshot ? (
              <img src={screenshot} alt="Mac App Screenshot" className="w-full h-full object-contain" />
            ) : (
              <div className="flex-1 bg-[#0D1117] p-3 text-white flex flex-col justify-between">
                <div className="h-4 w-28 bg-white/20 rounded" />
                <div className="h-16 bg-white/5 border border-white/10 rounded-lg p-2" />
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  // RENDER IPAD / TABLET FRAME
  if (isTablet) {
    return (
      <div
        className={`relative transition-transform duration-200 select-none ${getShadow()} ${className}`}
        style={{
          transform: transform3d,
          transformOrigin: 'center center',
          transformStyle: 'preserve-3d',
        }}
      >
        <div className={`relative w-[340px] h-[460px] rounded-[36px] p-[10px] ${getBezelGradient()}`}>
          <div className="relative w-full h-full bg-black rounded-[28px] overflow-hidden shadow-inner ring-1 ring-black">
            <div className="absolute top-2 left-1/2 -translate-x-1/2 w-2 h-2 rounded-full bg-[#151515] ring-1 ring-white/10" />
            {screenshot ? (
              <img src={screenshot} alt="Tablet Screenshot" className="w-full h-full object-cover object-top" />
            ) : (
              <div className="w-full h-full bg-[#090D16] text-white p-4 pt-8 flex flex-col justify-between">
                <div className="h-5 w-28 bg-white/20 rounded-md" />
                <div className="h-28 bg-gradient-to-br from-indigo-500/20 to-purple-500/20 border border-white/10 rounded-xl p-3" />
                <div className="w-24 h-1 bg-white/30 rounded-full mx-auto" />
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  // DEFAULT: PHONE CHASSIS (IPHONE / ANDROID)
  return (
    <div
      className={`relative transition-transform duration-200 select-none ${getShadow()} ${className}`}
      style={{
        transform: transform3d,
        transformOrigin: 'center center',
        transformStyle: 'preserve-3d',
      }}
    >
      {/* Outer Chassis */}
      <div className={`relative w-[340px] h-[720px] rounded-[56px] p-[10px] ${getBezelGradient()} shadow-inner`}>
        {/* Antenna bands */}
        <div className="absolute top-[80px] -left-[2px] w-[3px] h-[8px] bg-black/40 rounded-r-sm" />
        <div className="absolute top-[80px] -right-[2px] w-[3px] h-[8px] bg-black/40 rounded-l-sm" />
        <div className="absolute bottom-[120px] -left-[2px] w-[3px] h-[8px] bg-black/40 rounded-r-sm" />
        <div className="absolute bottom-[120px] -right-[2px] w-[3px] h-[8px] bg-black/40 rounded-l-sm" />

        {/* Buttons */}
        <div className="absolute top-[115px] -left-[4px] w-[4px] h-[28px] bg-[#2E2E32] rounded-l-sm" />
        <div className="absolute top-[160px] -left-[4px] w-[4px] h-[50px] bg-[#2E2E32] rounded-l-sm" />
        <div className="absolute top-[225px] -left-[4px] w-[4px] h-[50px] bg-[#2E2E32] rounded-l-sm" />
        <div className="absolute top-[175px] -right-[4px] w-[4px] h-[75px] bg-[#2E2E32] rounded-r-sm" />

        {/* Inner Screen Bezel */}
        <div className="relative w-full h-full bg-black rounded-[46px] overflow-hidden shadow-inner ring-1 ring-black">
          {/* Dynamic Island or Android Punch-Hole */}
          {isAndroidPhone ? (
            <div className="absolute top-[14px] left-1/2 -translate-x-1/2 w-3.5 h-3.5 bg-black rounded-full z-30 ring-1 ring-[#2A2A2E] flex items-center justify-center">
              <div className="w-1.5 h-1.5 rounded-full bg-[#111827]" />
            </div>
          ) : (
            <div className="absolute top-[11px] left-1/2 -translate-x-1/2 w-[98px] h-[28px] bg-black rounded-full z-30 flex items-center justify-between px-3 ring-1 ring-[#1C1C1E]">
              <div className="w-[10px] h-[10px] rounded-full bg-[#0A0D18] ring-1 ring-[#181E33] flex items-center justify-center">
                <div className="w-[4px] h-[4px] rounded-full bg-[#1A2645]/80" />
              </div>
              <div className="w-[8px] h-[8px] rounded-full bg-[#0B0D13] opacity-80" />
            </div>
          )}

          {/* Screenshot Content or High-Fidelity Mock Placeholder */}
          {screenshot ? (
            <img
              src={screenshot}
              alt="App Screenshot"
              className="w-full h-full object-cover object-top"
              crossOrigin="anonymous"
            />
          ) : (
            <div className="w-full h-full bg-[#090D16] text-white p-5 pt-12 flex flex-col justify-between font-sans">
              <div>
                <div className="flex items-center justify-between text-xs text-white/50 mb-6">
                  <span>9:41</span>
                  <div className="flex items-center space-x-1">
                    <span className="w-2.5 h-2.5 rounded-full bg-white/40" />
                    <span className="w-2.5 h-2.5 rounded-full bg-white/40" />
                    <span className="w-4 h-2.5 border border-white/40 rounded-sm" />
                  </div>
                </div>

                <div className="space-y-4">
                  <div className="h-6 w-32 bg-white/20 rounded-md animate-pulse" />
                  <div className="h-32 bg-gradient-to-br from-indigo-500/20 to-purple-500/20 border border-white/10 rounded-2xl p-4 flex flex-col justify-between">
                    <div className="h-4 w-24 bg-white/30 rounded" />
                    <div className="flex items-baseline space-x-2">
                      <span className="text-3xl font-bold tracking-tight">87%</span>
                      <span className="text-xs text-emerald-400 font-medium">+14% vs last week</span>
                    </div>
                    <div className="h-2 w-full bg-white/10 rounded-full overflow-hidden">
                      <div className="h-full bg-gradient-to-r from-indigo-500 to-emerald-400 w-[87%]" />
                    </div>
                  </div>

                  <div className="space-y-2 pt-2">
                    <div className="h-14 bg-white/5 border border-white/5 rounded-xl p-3 flex items-center justify-between">
                      <div className="flex items-center space-x-3">
                        <div className="w-8 h-8 rounded-lg bg-indigo-500/30 flex items-center justify-center text-xs">⚡️</div>
                        <div className="space-y-1">
                          <div className="h-3 w-20 bg-white/40 rounded" />
                          <div className="h-2 w-12 bg-white/20 rounded" />
                        </div>
                      </div>
                      <span className="text-xs font-semibold text-indigo-300">Active</span>
                    </div>

                    <div className="h-14 bg-white/5 border border-white/5 rounded-xl p-3 flex items-center justify-between">
                      <div className="flex items-center space-x-3">
                        <div className="w-8 h-8 rounded-lg bg-pink-500/30 flex items-center justify-center text-xs">🎯</div>
                        <div className="space-y-1">
                          <div className="h-3 w-24 bg-white/40 rounded" />
                          <div className="h-2 w-16 bg-white/20 rounded" />
                        </div>
                      </div>
                      <span className="text-xs font-semibold text-emerald-400">Done</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Home indicator bar */}
              <div className="w-32 h-1 bg-white/30 rounded-full mx-auto mb-1" />
            </div>
          )}

          {/* Screen Glare Overlay */}
          <div className="pointer-events-none absolute inset-0 bg-gradient-to-tr from-transparent via-white/[0.04] to-transparent" />
        </div>
      </div>
    </div>
  );
};
