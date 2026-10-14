import { describe, expect, it } from 'vitest';
import { COPY_FORMULAS } from './copyFormulas';

describe('copyFormulas playbook', () => {
  it('should provide structured formulas with valid categories and roles', () => {
    expect(COPY_FORMULAS.length).toBeGreaterThanOrEqual(5);
    for (const formula of COPY_FORMULAS) {
      expect(typeof formula.category).toBe('string');
      expect(formula.category.length).toBeGreaterThan(0);
      expect(['Hero', 'Feature', 'Benefit', 'Stats', 'Ecosystem', 'CTA']).toContain(formula.role);
      expect(typeof formula.headline).toBe('string');
      expect(formula.headline.length).toBeGreaterThan(0);
      expect(typeof formula.subheadline).toBe('string');
      expect(formula.subheadline.length).toBeGreaterThan(0);
    }
  });

  it('includes developer & macOS native formulas', () => {
    const devFormulas = COPY_FORMULAS.filter(f => f.category.includes('Developer'));
    expect(devFormulas.length).toBeGreaterThanOrEqual(3);
  });
});
