import React, { useState } from 'react';
import { TargetDevice, TARGET_DIMENSIONS } from '../types';
import { STYLE_PRESETS } from '../stylePresets';
import { COPY_FORMULAS, CopyFormula } from '../copyFormulas';
import { Smartphone, Globe, Layers, Download, CheckCircle, Sparkles, Palette, Lightbulb, Save, Loader2 } from 'lucide-react';

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
  stylePreset?: string;
  onStylePresetChange?: (presetId: string) => void;
  isDirty?: boolean;
  isSaving?: boolean;
  onSaveConfig?: () => void;
  onApplyCopyFormula?: (formula: CopyFormula) => void;
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
  stylePreset,
  onStylePresetChange,
  isDirty = false,
  isSaving = false,
  onSaveConfig,
  onApplyCopyFormula,
}) => {
  const currentDim = TARGET_DIMENSIONS[currentTarget];
  const [showCopyMenu, setShowCopyMenu] = useState(false);

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

        {/* Style Preset Selector */}
        {onStylePresetChange && (
          <div className="flex items-center space-x-1.5 bg-white/5 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs">
            <Palette className="w-3.5 h-3.5 text-pink-400" />
            <select
              value={stylePreset || ''}
              onChange={(e) => onStylePresetChange(e.target.value)}
              className="bg-transparent text-white focus:outline-none cursor-pointer font-medium max-w-[130px] truncate"
            >
              <option value="" className="bg-[#181C26] text-white">Theme: Custom</option>
              {Object.values(STYLE_PRESETS).map((p) => (
                <option key={p.id} value={p.id} className="bg-[#181C26] text-white">
                  {p.name}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Copy Ideas Menu */}
        {onApplyCopyFormula && (
          <div className="relative">
            <button
              onClick={() => setShowCopyMenu(!showCopyMenu)}
              className="flex items-center space-x-1.5 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-amber-300 font-medium transition-all"
              title="Marketing Headline Formulas"
            >
              <Lightbulb className="w-3.5 h-3.5 text-amber-400" />
              <span>Copy Ideas</span>
            </button>
            {showCopyMenu && (
              <div className="absolute top-full mt-2 left-0 w-80 bg-[#161B26] border border-white/15 rounded-xl shadow-2xl p-2 z-50 flex flex-col space-y-1">
                <span className="text-[10px] uppercase font-mono tracking-wider text-white/40 px-2 py-1">Headline Formulas</span>
                {COPY_FORMULAS.map((f, i) => (
                  <button
                    key={i}
                    onClick={() => {
                      onApplyCopyFormula(f);
                      setShowCopyMenu(false);
                    }}
                    className="text-left px-2.5 py-1.5 hover:bg-white/10 rounded-lg text-xs flex flex-col transition-all"
                  >
                    <span className="font-semibold text-white flex items-center justify-between">
                      {f.headline}
                      <span className="text-[9px] uppercase font-mono text-blue-400 bg-blue-500/10 px-1 rounded">{f.role}</span>
                    </span>
                    <span className="text-[11px] text-white/60 line-clamp-1">{f.subheadline}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Right Action Buttons */}
      <div className="flex items-center space-x-3">
        <div className="flex items-center space-x-1.5 text-xs text-white/50 font-mono">
          <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
          <span>{cardCount} Cards Ready</span>
        </div>

        {onSaveConfig && (
          <button
            onClick={onSaveConfig}
            disabled={isSaving || !isDirty}
            className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold shadow-md active:scale-95 transition-all ${
              isDirty
                ? 'bg-emerald-600 hover:bg-emerald-500 text-white'
                : 'bg-white/5 text-white/40 border border-white/10 cursor-not-allowed'
            }`}
            title="Save changes back to creative.config.json"
          >
            {isSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
            <span>{isSaving ? 'Saving...' : isDirty ? 'Save Config *' : 'Saved'}</span>
          </button>
        )}

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
