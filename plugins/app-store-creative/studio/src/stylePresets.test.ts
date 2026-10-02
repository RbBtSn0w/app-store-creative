import { describe, it, expect } from 'vitest';
import { STYLE_PRESETS, StylePresetId } from './stylePresets';

describe('stylePresets definitions and contrast safety', () => {
  const expectedPresetIds: StylePresetId[] = [
    'liquid_glass',
    'swiss_grid',
    'midnight_glow',
    'quiet_japandi',
    'bento_keynote',
    'candy_pop',
    'neon_athletic',
    'magazine_editorial',
    'soft_clay',
    'pastel_dream',
    'vintage_travel',
    'cyber_matrix',
    'clean_light',
    'dark_contrast',
    'ocean_gradient',
    'sunset_warmth',
    'forest_minimal',
    'monochrome_bold',
  ];

  it('should have exactly 18 presets matching the schema', () => {
    const keys = Object.keys(STYLE_PRESETS) as StylePresetId[];
    expect(keys.length).toBe(18);
    expect(keys.sort()).toEqual([...expectedPresetIds].sort());
  });

  it('each preset should have valid id, name, category, and theme', () => {
    for (const [id, preset] of Object.entries(STYLE_PRESETS)) {
      expect(preset.id).toBe(id);
      expect(preset.name.trim().length).toBeGreaterThan(0);
      expect(preset.category.trim().length).toBeGreaterThan(0);
      expect(preset.theme).toBeDefined();

      // Check background definition
      const bg = preset.theme.background;
      expect(bg).toBeDefined();
      expect(['solid', 'gradient']).toContain(bg?.type);
      expect(Array.isArray(bg?.colors)).toBe(true);
      expect(bg?.colors.length).toBeGreaterThan(0);

      // Verify colors format (hex, rgb, or named)
      for (const color of bg!.colors) {
        expect(typeof color).toBe('string');
        expect(color.length).toBeGreaterThan(0);
      }

      // Check typography colors
      expect(preset.theme.headlineColor).toBeDefined();
      expect(preset.theme.subheadlineColor).toBeDefined();

      // Check bezel and shadow values
      expect(['natural', 'titanium_black', 'titanium_natural', 'silver', 'midnight', 'flat']).toContain(
        preset.theme.bezelStyle
      );
      expect(['soft', 'dramatic', 'subtle', 'none']).toContain(preset.theme.shadow);
    }
  });

  it('solid presets should have at least 1 color', () => {
    for (const preset of Object.values(STYLE_PRESETS)) {
      if (preset.theme.background?.type === 'solid') {
        expect(preset.theme.background.colors.length).toBeGreaterThanOrEqual(1);
      }
    }
  });

  it('gradient presets should have at least 2 colors and valid angle', () => {
    for (const preset of Object.values(STYLE_PRESETS)) {
      if (preset.theme.background?.type === 'gradient') {
        expect(preset.theme.background.colors.length).toBeGreaterThanOrEqual(2);
        expect(typeof preset.theme.background.angle).toBe('number');
      }
    }
  });
});
