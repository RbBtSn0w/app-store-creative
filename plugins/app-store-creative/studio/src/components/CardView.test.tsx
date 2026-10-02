import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { CardView } from './CardView';

const render = (index: number, connected: boolean, customBackground = false) => renderToStaticMarkup(
  <CardView card={{ id: 'history', headline: 'Find your clips', screenshot: '/history.png',
    ...(customBackground ? { customBackground: { type: 'solid' as const, colors: ['#ffffff'] } } : {}) }}
    index={index} totalCards={5} connected={connected} target="mac_16_10"
    theme={{ stylePreset: 'liquid_glass', background: { type: 'solid', colors: ['#000000'] } }} isExport />
);

describe('connected screenshot backgrounds', () => {
  it('exports successive slices of one full-width background', () => {
    expect(render(0, true)).toContain('data-background-track="connected"');
    expect(render(0, true)).toContain('width:3600px');
    expect(render(1, true)).toContain('left:-720px');
    expect(render(4, true)).toContain('left:-2880px');
  });
  it('preserves independent backgrounds when disconnected or customized', () => {
    expect(render(1, false)).toContain('data-background-track="isolated"');
    expect(render(1, false)).not.toContain('left:-720px');
    expect(render(1, true, true)).toContain('data-background-track="isolated"');
  });
});

it('uses side composition only for native Mac layouts', () => {
  const card = { id: 'quick-paste', headline: 'Paste without switching', screenshot: '/panel.png', layout: 'mac_native_left' as const };
  const theme = { background: { type: 'solid' as const, colors: ['#111111'] } };
  const mac = renderToStaticMarkup(<CardView card={card} index={0} target="mac_16_10" theme={theme} isExport />);
  expect(mac).toContain('data-native-window="true"');
  expect(mac).toContain('max-height:360px');
  expect(mac).toContain('text-left w-[240px]');
  const phone = renderToStaticMarkup(<CardView card={card} index={0} target="iphone_6_9" theme={theme} isExport />);
  expect(phone).not.toContain('data-native-window="true"');
  expect(phone).not.toContain('text-left w-[240px]');
});
