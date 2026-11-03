import type { BackgroundConfig, CardConfig, CardOffset, CreativeConfig, LocalizedCard, TargetDevice } from './types';

export function defaultCardLayout(target: TargetDevice): NonNullable<CardConfig['layout']> {
  return target.startsWith('mac_') ? 'mac_native_hero' : 'phone_bottom';
}

export function localizedFields(config: CreativeConfig, card: CardConfig, target: TargetDevice, locale: string): LocalizedCard {
  return { ...config.localizations?.[locale]?.[card.id], ...card.variants?.[target]?.localizations?.[locale] };
}

export function resolveCard(config: CreativeConfig, card: CardConfig, target: TargetDevice, locale: string): CardConfig {
  const { localizations: _, ...variant } = card.variants?.[target] || {};
  const localized = localizedFields(config, card, target, locale);
  const deviceOffset = (variant.deviceOffset || card.deviceOffset)
    ? { ...(card.deviceOffset || {}), ...(variant.deviceOffset || {}) }
    : undefined;
  return { ...card, ...variant,
    headline: localized.headline ?? variant.headline ?? card.headline,
    subheadline: localized.subheadline ?? variant.subheadline ?? card.subheadline,
    screenshot: localized.screenshot ?? variant.screenshot ?? card.screenshot,
    deviceOffset };
}

export interface VariantMutation extends LocalizedCard {
  layout?: CardConfig['layout'];
  deviceOffset?: CardOffset;
  customBackground?: BackgroundConfig;
}

export function updateVariant(config: CreativeConfig, id: string, target: TargetDevice, locale: string,
  change: VariantMutation): CreativeConfig {
  return { ...config, cards: config.cards.map(card => {
    if (card.id !== id) return card;
    const variant = card.variants?.[target] || {};
    const { layout, deviceOffset, customBackground, ...text } = change;
    const isDefault = locale === (config.project.defaultLocale || 'en-US');
    const localized = localizedFields(config, card, target, locale);
    const defaultCopy: LocalizedCard = {};
    const directCopy: LocalizedCard = {};
    const localeCopy: LocalizedCard = {};
    for (const field of ['headline', 'subheadline', 'screenshot'] as const) {
      if (text[field] === undefined) continue;
      if (!isDefault || localized[field] !== undefined) localeCopy[field] = text[field];
      else if (field === 'screenshot' || variant[field] !== undefined) directCopy[field] = text[field];
      else defaultCopy[field] = text[field];
    }
    const updatedOffset = deviceOffset
      ? { ...(variant.deviceOffset || {}), ...deviceOffset }
      : variant.deviceOffset;
    const updated = isDefault
      ? { ...variant, ...directCopy, ...(layout ? { layout } : {}), ...(updatedOffset ? { deviceOffset: updatedOffset } : {}), ...(Object.keys(localeCopy).length ? {
          localizations: { ...variant.localizations,
            [locale]: { ...variant.localizations?.[locale], ...localeCopy } },
        } : {}) }
      : { ...variant, ...(layout ? { layout } : {}), ...(updatedOffset ? { deviceOffset: updatedOffset } : {}), localizations: {
        ...variant.localizations, [locale]: { ...variant.localizations?.[locale], ...text },
      } };
    return {
      ...card,
      ...defaultCopy,
      ...(customBackground ? { customBackground } : {}),
      variants: { ...card.variants, [target]: updated },
    };
  }) };
}
