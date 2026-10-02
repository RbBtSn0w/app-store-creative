import React from 'react';
import { TargetDevice, TARGET_DIMENSIONS } from '../types';
import { Smartphone, Globe, Layers, Download, CheckCircle, Sparkles } from 'lucide-react';

interface ToolbarProps {
  targets: TargetDevice[];
  currentTarget: TargetDevice;
  onTargetChange: (target: TargetDevice) => void;
  locales: string[];
  currentLocale: string;
  onLocaleChange: (locale: string) => void;
  connectedTrack: boolean;
  onToggleConnectedTrack: () => void;
  cardCount: number;
  onTriggerExport: () => void;
  isExporting?: boolean;
}

export const Toolbar: React.FC<ToolbarProps> = ({
  targets,
  currentTarget,
  onTargetChange,
  locales,
  currentLocale,
  onLocaleChange,
  connectedTrack,
  onToggleConnectedTrack,
  cardCount,
  onTriggerExport,
  isExporting = false,
}) => {
  const currentDim = TARGET_DIMENSIONS[currentTarget];

  return (
    <header className="sticky top-0 z-50 w-full bg-[#12151E]/90 backdrop-blur-md border-b border-white/10 px-6 py-3 flex items-center justify-between shadow-lg text-white">
      {/* Brand & Status */}
      <div className="flex items-center space-x-3">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-blue-600 to-indigo-500 flex items-center justify-center font-bold text-sm shadow-md">
          <Sparkles className="w-4 h-4 text-white" />
        </div>
        <div>
          <div className="flex items-center space-x-2">
            <span className="font-semibold tracking-tight text-sm">App Store Creative Studio</span>
            <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-300 border border-blue-500/30">
              v2.0
            </span>
          </div>
          <p className="text-[11px] text-white/50">Localhost Canvas • Agent-Native Release Studio</p>
        </div>
      </div>

      {/* Center Controls */}
      <div className="flex items-center space-x-3">
        {/* Device / Target Selector */}
        <div className="flex items-center space-x-1.5 bg-white/5 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs">
          <Smartphone className="w-3.5 h-3.5 text-blue-400" />
          <select
            value={currentTarget}
            onChange={(e) => onTargetChange(e.target.value as TargetDevice)}
            className="bg-transparent text-white focus:outline-none cursor-pointer font-medium"
          >
            {targets.map((t) => (
              <option key={t} value={t} className="bg-[#181C26] text-white">
                {TARGET_DIMENSIONS[t].displayName}
              </option>
            ))}
          </select>
          <span className="text-[10px] text-white/40 font-mono ml-1">
            {currentDim.width}×{currentDim.height}
          </span>
        </div>

        {/* Locale Selector */}
        {locales.length > 1 && (
          <div className="flex items-center space-x-1.5 bg-white/5 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs">
            <Globe className="w-3.5 h-3.5 text-emerald-400" />
            <select
              value={currentLocale}
              onChange={(e) => onLocaleChange(e.target.value)}
              className="bg-transparent text-white focus:outline-none cursor-pointer font-medium"
            >
              {locales.map((l) => (
                <option key={l} value={l} className="bg-[#181C26] text-white">
                  {l}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Connected Track Toggle */}
        <button
          onClick={onToggleConnectedTrack}
          className={`flex items-center space-x-1.5 px-2.5 py-1.5 rounded-lg border text-xs font-medium transition-all ${
            connectedTrack
              ? 'bg-indigo-600/30 border-indigo-500/60 text-indigo-200'
              : 'bg-white/5 border-white/10 text-white/60 hover:text-white'
          }`}
          title="Toggle Continuous Panorama Track"
        >
          <Layers className="w-3.5 h-3.5" />
          <span>Connected Canvas</span>
        </button>
      </div>

      {/* Right Action Buttons */}
      <div className="flex items-center space-x-3">
        <div className="flex items-center space-x-1.5 text-xs text-white/50 font-mono">
          <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
          <span>{cardCount} Cards Ready</span>
        </div>

        <button
          onClick={onTriggerExport}
          disabled={isExporting}
          className="flex items-center space-x-2 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white px-3.5 py-1.5 rounded-lg text-xs font-semibold shadow-md active:scale-95 transition-all disabled:opacity-50"
        >
          <Download className="w-3.5 h-3.5" />
          <span>{isExporting ? 'Exporting...' : 'Export 1:1 Bundle'}</span>
        </button>
      </div>
    </header>
  );
};
