import type { CardConfig, CreativeConfig, LocalizedCard, TargetDevice } from './types';

export function defaultCardLayout(target: TargetDevice): NonNullable<CardConfig['layout']> {
  return target.startsWith('mac_') ? 'mac_native_hero' : 'phone_bottom';
}

export function localizedFields(config: CreativeConfig, card: CardConfig, target: TargetDevice, locale: string): LocalizedCard {
  return { ...config.localizations?.[locale]?.[card.id], ...card.variants?.[target]?.localizations?.[locale] };
}

export function resolveCard(config: CreativeConfig, card: CardConfig, target: TargetDevice, locale: string): CardConfig {
  const { localizations: _, ...variant } = card.variants?.[target] || {};
  const localized = localizedFields(config, card, target, locale);
  return { ...card, ...variant,
    headline: localized.headline ?? card.headline,
    subheadline: localized.subheadline ?? card.subheadline,
    screenshot: localized.screenshot ?? variant.screenshot ?? card.screenshot };
}

export function updateVariant(config: CreativeConfig, id: string, target: TargetDevice, locale: string,
  change: LocalizedCard & { layout?: CardConfig['layout'] }): CreativeConfig {
  return { ...config, cards: config.cards.map(card => {
    if (card.id !== id) return card;
    const variant = card.variants?.[target] || {};
    const { layout, ...text } = change;
    const { headline: _headline, subheadline: _subheadline, ...capture } = text;
    const existingDefault = locale === (config.project.defaultLocale || 'en-US') &&
      Object.keys(localizedFields(config, card, target, locale)).length > 0;
    const updated = locale === (config.project.defaultLocale || 'en-US')
      ? { ...variant, ...capture, ...(layout ? { layout } : {}), ...(existingDefault ? {
          localizations: { ...variant.localizations,
            [locale]: { ...variant.localizations?.[locale], ...text } },
        } : {}) }
      : { ...variant, ...(layout ? { layout } : {}), localizations: {
        ...variant.localizations, [locale]: { ...variant.localizations?.[locale], ...text },
      } };
    // Default copy remains shared unless a locale override is explicit.
    const defaultCopy = locale === (config.project.defaultLocale || 'en-US')
      ? { ...(text.headline !== undefined ? { headline: text.headline } : {}),
          ...(text.subheadline !== undefined ? { subheadline: text.subheadline } : {}) } : {};
    return { ...card, ...defaultCopy, variants: { ...card.variants, [target]: updated } };
  }) };
}
