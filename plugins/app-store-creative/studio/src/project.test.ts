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
  it('updates deviceOffset scoped to target without polluting other targets', () => {
    const edited = updateVariant(config, 'hero', 'iphone_6_9', 'en-US', {
      deviceOffset: { scale: 1.05, rotate: -5, rotateX: 10 },
    });
    const phoneCard = resolveCard(edited, edited.cards[0], 'iphone_6_9', 'en-US');
    const macCard = resolveCard(edited, edited.cards[0], 'mac_16_10', 'en-US');

    expect(phoneCard.deviceOffset).toEqual({ scale: 1.05, rotate: -5, rotateX: 10 });
    expect(macCard.deviceOffset).toBeUndefined();
  });
  it('merges card-level baseline offset with target-specific variant offset', () => {
    const withBase: CreativeConfig = {
      ...config,
      cards: [{
        ...config.cards[0],
        deviceOffset: { x: 0, y: 20, scale: 1.0 },
      }],
    };
    const edited = updateVariant(withBase, 'hero', 'mac_16_10', 'en-US', {
      deviceOffset: { rotate: 2, scale: 1.08 },
    });
    const macCard = resolveCard(edited, edited.cards[0], 'mac_16_10', 'en-US');
    expect(macCard.deviceOffset).toEqual({ x: 0, y: 20, scale: 1.08, rotate: 2 });
    expect(edited.cards[0].variants?.mac_16_10?.deviceOffset).toEqual({ rotate: 2, scale: 1.08 });
  });
  it('updates customBackground on the card', () => {
    const edited = updateVariant(config, 'hero', 'mac_16_10', 'en-US', {
      customBackground: { type: 'gradient', colors: ['#000', '#fff'], angle: 90 },
    });
    expect(edited.cards[0].customBackground).toEqual({ type: 'gradient', colors: ['#000', '#fff'], angle: 90 });
  });
  it('resolves variant headline and subheadline when specified', () => {
    const withVariantCopy: CreativeConfig = {
      ...config,
      cards: [{
        ...config.cards[0],
        variants: {
          mac_16_10: {
            headline: 'Mac Hero Headline',
            subheadline: 'Mac Hero Subheadline',
          },
        },
      }],
    };
    const resolved = resolveCard(withVariantCopy, withVariantCopy.cards[0], 'mac_16_10', 'en-US');
    expect(resolved.headline).toBe('Mac Hero Headline');
    expect(resolved.subheadline).toBe('Mac Hero Subheadline');
  });
});

