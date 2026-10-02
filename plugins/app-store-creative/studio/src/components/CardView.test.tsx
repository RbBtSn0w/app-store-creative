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
