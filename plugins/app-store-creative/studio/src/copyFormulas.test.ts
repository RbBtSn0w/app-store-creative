import { describe, it, expect } from 'vitest';
import { COPY_FORMULAS } from './copyFormulas';

describe('copyFormulas data structure and narrative coverage', () => {
  const requiredRoles = ['Hero', 'Feature', 'Benefit', 'Stats', 'CTA'];

  it('should have a rich collection of copy formulas', () => {
    expect(COPY_FORMULAS.length).toBeGreaterThanOrEqual(10);
  });

  it('all copy formulas should have valid category, role, headline and subheadline', () => {
    for (const formula of COPY_FORMULAS) {
      expect(formula.category.trim().length).toBeGreaterThan(0);
      expect(requiredRoles).toContain(formula.role);
      expect(formula.headline.trim().length).toBeGreaterThan(0);
      expect(formula.subheadline.trim().length).toBeGreaterThan(0);

      // Verify length constraints suitable for store cards
      expect(formula.headline.length).toBeLessThanOrEqual(50);
      expect(formula.subheadline.length).toBeLessThanOrEqual(120);
    }
  });

  it('covers key App Store categories', () => {
    const categories = new Set(COPY_FORMULAS.map((f) => f.category));
    expect(categories.has('Habit & Productivity')).toBe(true);
    expect(categories.has('Finance & Budget')).toBe(true);
    expect(categories.has('Fitness & Health')).toBe(true);
    expect(categories.has('AI & Developer Tools')).toBe(true);
  });

  it('covers the essential 5-act narrative roles across the library', () => {
    const presentRoles = new Set(COPY_FORMULAS.map((f) => f.role));
    for (const role of requiredRoles) {
      expect(presentRoles.has(role as any)).toBe(true);
    }
  });
});
