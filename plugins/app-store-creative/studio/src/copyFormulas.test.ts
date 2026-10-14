import { describe, expect, it } from 'vitest';
import { COPY_FORMULAS } from './copyFormulas';

describe('copyFormulas playbook', () => {
  it('should provide structured formulas with valid categories and roles', () => {
    expect(COPY_FORMULAS.length).toBeGreaterThanOrEqual(5);
    const validRoles = ['Hero', 'Mechanism', 'Depth', 'Ecosystem', 'CTA', 'Feature', 'Benefit', 'Stats'];
    for (const formula of COPY_FORMULAS) {
      expect(typeof formula.category).toBe('string');
      expect(formula.category.length).toBeGreaterThan(0);
      expect(validRoles).toContain(formula.role);
      expect(typeof formula.headline).toBe('string');
      expect(formula.headline.length).toBeGreaterThan(0);
      expect(typeof formula.subheadline).toBe('string');
      expect(formula.subheadline.length).toBeGreaterThan(0);
    }
  });

  it('includes developer & macOS native formulas with complete 5-slide arc', () => {
    const devFormulas = COPY_FORMULAS.filter(f => f.category.includes('Developer'));
    expect(devFormulas.length).toBe(5);
    const roles = devFormulas.map(f => f.role);
    expect(roles).toEqual(['Hero', 'Mechanism', 'Depth', 'Ecosystem', 'CTA']);
  });

  it('covers the standard 5-slide arc roles across the entire playbook', () => {
    const roles = new Set(COPY_FORMULAS.map(f => f.role));
    expect(roles.has('Hero')).toBe(true);
    expect(roles.has('Mechanism')).toBe(true);
    expect(roles.has('Depth')).toBe(true);
    expect(roles.has('Ecosystem')).toBe(true);
    expect(roles.has('CTA')).toBe(true);
  });
});
