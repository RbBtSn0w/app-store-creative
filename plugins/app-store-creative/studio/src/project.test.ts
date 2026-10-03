import { describe, expect, it } from 'vitest';
import { resolveCard, updateVariant } from './project';
import type { CreativeConfig } from './types';

const config: CreativeConfig = {
  project: { id: 'demo', name: 'Demo', bundleId: 'com.example.demo', defaultLocale: 'en-US', locales: ['en-US', 'zh-Hans'] },
  targets: ['iphone_6_9', 'mac_16_10'], theme: { background: { type: 'solid', colors: ['#111'] } },
  cards: [{ id: 'hero', headline: 'English', screenshot: '/phone.png', variants: {
    mac_16_10: { screenshot: '/desktop.png', layout: 'mac_native_hero', localizations: {
      'zh-Hans': { headline: 'Chinese desktop', screenshot: '/desktop-zh.png', subheadline: '' },
    } },
  } }],
};

describe('reviewed target and locale assignments', () => {
  it.each(['target', 'project'])('edits existing %s default-language overrides', scope => {
    const existing = structuredClone(config);
    const fields = { headline: 'Old text', screenshot: '/old.png' };
    if (scope === 'target') existing.cards[0].variants!.mac_16_10!.localizations!['en-US'] = fields;
    else existing.localizations = { 'en-US': { hero: fields } };
    const edited = updateVariant(existing, 'hero', 'mac_16_10', 'en-US', {
      headline: 'New text', subheadline: '', screenshot: '/new.png',
    });
    const resolved = resolveCard(edited, edited.cards[0], 'mac_16_10', 'en-US');
    expect(resolved.headline).toBe('New text');
    expect(resolved.screenshot).toBe('/new.png');
    expect(resolved.subheadline).toBe('');
    expect(resolveCard(existing, existing.cards[0], 'mac_16_10', 'en-US').headline).toBe('Old text');
  });
  it('resolves the actual target capture and preserves deliberately empty optional copy', () => {
    const card = resolveCard(config, config.cards[0], 'mac_16_10', 'zh-Hans');
    expect(card.screenshot).toBe('/desktop-zh.png');
    expect(card.subheadline).toBe('');
    expect(card.layout).toBe('mac_native_hero');
  });
  it('editing Chinese desktop copy does not alter English or phone copy', () => {
    const edited = updateVariant(config, 'hero', 'mac_16_10', 'zh-Hans', { headline: 'New Chinese' });
    expect(resolveCard(edited, edited.cards[0], 'mac_16_10', 'en-US').headline).toBe('English');
    expect(resolveCard(edited, edited.cards[0], 'iphone_6_9', 'en-US').screenshot).toBe('/phone.png');
    expect(resolveCard(config, config.cards[0], 'mac_16_10', 'zh-Hans').headline).toBe('Chinese desktop');
  });
  it('keeps default copy shared across targets after sequential edits', () => {
    const first = updateVariant(config, 'hero', 'mac_16_10', 'en-US', { headline: 'First edit' });
    const second = updateVariant(first, 'hero', 'iphone_6_9', 'en-US', { headline: 'Latest edit' });
    expect(second.cards[0].variants?.mac_16_10).not.toHaveProperty('headline');
    expect(resolveCard(second, second.cards[0], 'mac_16_10', 'en-US').headline).toBe('Latest edit');
  });

});
