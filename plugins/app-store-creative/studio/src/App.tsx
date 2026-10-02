import React, { useState, useEffect } from 'react';
import { CreativeConfig, TargetDevice, TARGET_DIMENSIONS } from './types';
import { CardView } from './components/CardView';
import { Toolbar } from './components/Toolbar';

// Fallback sample config when running standalone
const DEFAULT_CONFIG: CreativeConfig = {
  project: {
    id: 'habit-flow',
    name: 'HabitFlow',
    bundleId: 'com.example.habitflow',
    defaultLocale: 'en-US',
    locales: ['en-US', 'zh-Hans'],
  },
  targets: ['iphone_6_9', 'iphone_6_5'],
  theme: {
    background: {
      type: 'gradient',
      colors: ['#0A0E1A', '#1E1B4B', '#311042'],
      angle: 145,
    },
    fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Display', sans-serif",
    headlineColor: '#FFFFFF',
    subheadlineColor: 'rgba(255, 255, 255, 0.75)',
    bezelStyle: 'natural',
    shadow: 'dramatic',
  },
  connectedTrack: true,
  cards: [
    {
      id: '01-hero',
      headline: 'Build Habits That Last',
      subheadline: 'Effortless tracking designed for Apple platforms',
      layout: 'phone_bottom',
      deviceOffset: { x: 0, y: 30, scale: 1.05, rotate: 0 },
    },
    {
      id: '02-analytics',
      headline: 'Insights at a Glance',
      subheadline: 'Interactive streaks and smart completion heatmaps',
      layout: 'phone_tilt_left',
      deviceOffset: { x: -15, y: 50, scale: 1.0, rotate: -4 },
    },
    {
      id: '03-widgets',
      headline: 'Right on Your Lock Screen',
      subheadline: 'StandBy mode and interactive widgets ready',
      layout: 'phone_tilt_right',
      deviceOffset: { x: 15, y: 50, scale: 1.0, rotate: 4 },
    },
  ],
  localizations: {
    'zh-Hans': {
      '01-hero': {
        headline: '培养持久好习惯',
        subheadline: '专为 Apple 生态打造的极简习惯追踪',
      },
      '02-analytics': {
        headline: '数据洞察，一目了然',
        subheadline: '连续打卡天数与智能完成度热力图',
      },
      '03-widgets': {
        headline: '锁屏微件，触手可及',
        subheadline: '支持待机显示与交互式桌面小组件',
      },
    },
  },
};

export const App: React.FC = () => {
  const [config, setConfig] = useState<CreativeConfig>(DEFAULT_CONFIG);
  const [currentTarget, setCurrentTarget] = useState<TargetDevice>('iphone_6_9');
  const [currentLocale, setCurrentLocale] = useState<string>('en-US');
  const [connectedTrack, setConnectedTrack] = useState<boolean>(true);
  const [isExporting, setIsExporting] = useState<boolean>(false);

  // Check query params for export mode
  const urlParams = new URLSearchParams(window.location.search);
  const isExport = urlParams.get('export') === 'true';
  const exportCardParam = urlParams.get('card');
  const exportTargetParam = (urlParams.get('target') as TargetDevice) || 'iphone_6_9';
  const exportLocaleParam = urlParams.get('locale') || 'en-US';

  // Fetch dynamic config from backend API if available
  useEffect(() => {
    fetch('/api/config')
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data) {
          setConfig(data);
          if (data.targets?.length) setCurrentTarget(data.targets[0]);
          if (data.project?.defaultLocale) setCurrentLocale(data.project.defaultLocale);
          if (typeof data.connectedTrack === 'boolean') setConnectedTrack(data.connectedTrack);
        }
      })
      .catch(() => {
        // Standalone mode, default config is active
      });
  }, []);

  // EXPORT MODE: Render only the requested card at 100% viewport size
  if (isExport && exportCardParam !== null) {
    const cardIndex = isNaN(Number(exportCardParam))
      ? config.cards.findIndex((c) => c.id === exportCardParam)
      : Number(exportCardParam);

    const card = config.cards[cardIndex] || config.cards[0];
    const localized = config.localizations?.[exportLocaleParam]?.[card.id];

    return (
      <div className="w-screen h-screen m-0 p-0 overflow-hidden bg-black select-none">
        <CardView
          card={card}
          index={cardIndex}
          totalCards={config.cards.length}
          target={exportTargetParam}
          theme={config.theme}
          locale={exportLocaleParam}
          localizedText={localized}
          isExport={true}
          connected={config.connectedTrack}
        />
      </div>
    );
  }

  // INTERACTIVE STUDIO MODE
  const handleTriggerExport = () => {
    setIsExporting(true);
    fetch('/api/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target: currentTarget, locale: currentLocale }),
    })
      .then((res) => res.json())
      .then((res) => {
        alert(res.message || 'Export initiated! Check your artifacts folder.');
      })
      .catch(() => {
        alert('Tip: To export store-ready 1:1 screenshots, run "app-store-creative export" in terminal.');
      })
      .finally(() => setIsExporting(false));
  };

  return (
    <div className="min-h-screen bg-[#0B0D13] flex flex-col text-slate-100 font-sans selection:bg-blue-500 selection:text-white">
      {/* Top Application Toolbar */}
      <Toolbar
        targets={config.targets || ['iphone_6_9']}
        currentTarget={currentTarget}
        onTargetChange={setCurrentTarget}
        locales={config.project.locales || ['en-US']}
        currentLocale={currentLocale}
        onLocaleChange={setCurrentLocale}
        connectedTrack={connectedTrack}
        onToggleConnectedTrack={() => setConnectedTrack(!connectedTrack)}
        cardCount={config.cards.length}
        onTriggerExport={handleTriggerExport}
        isExporting={isExporting}
      />

      {/* Main Studio Viewport */}
      <main className="flex-1 flex flex-col items-center justify-center p-8 overflow-x-auto">
        <div className="mb-4 text-center">
          <span className="text-xs uppercase tracking-widest text-white/40 font-mono">
            {config.project.name} • {TARGET_DIMENSIONS[currentTarget].displayName} • {currentLocale}
          </span>
        </div>

        {/* Continuous Card Track */}
        <div
          className={`flex items-center gap-6 p-6 rounded-[40px] transition-all duration-300 ${
            connectedTrack
              ? 'bg-gradient-to-r from-indigo-950/20 via-purple-950/20 to-indigo-950/20 border border-white/10 shadow-2xl backdrop-blur-xl'
              : ''
          }`}
        >
          {config.cards.map((card, idx) => {
            const localized = config.localizations?.[currentLocale]?.[card.id];
            return (
              <CardView
                key={card.id}
                card={card}
                index={idx}
                totalCards={config.cards.length}
                target={currentTarget}
                theme={config.theme}
                locale={currentLocale}
                localizedText={localized}
                connected={connectedTrack}
                isExport={false}
              />
            );
          })}
        </div>

        {/* Bottom Helpful Guide */}
        <footer className="mt-8 text-center text-xs text-white/40 max-w-xl">
          <p>
            Connected Canvas active. You can edit <code className="text-blue-400 font-mono">creative.config.json</code> to
            update marketing copy, change gradient angles, or adjust device tilts. Hot reload will instantly reflect changes.
          </p>
        </footer>
      </main>
    </div>
  );
};
