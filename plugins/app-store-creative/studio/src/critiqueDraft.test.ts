import { describe, expect, it } from 'vitest';
import { critiqueDraft, critiqueSaveNotice, currentCritiqueSession, initialCritiqueDraft } from './critiqueDraft';

const started = () => critiqueDraft(initialCritiqueDraft(), { type: 'start' });

describe('critique drafts', () => {
  it('retains each card save notice independently across interleaved saves and edits', () => {
    let state = started();
    state = critiqueDraft(state, { type: 'edit', cardId: 'hero', notes: 'Submitted' });
    state = critiqueDraft(state, { type: 'edit', cardId: 'hero', notes: 'Newer' });
    state = critiqueDraft(state, { type: 'saved', generation: state.generation, cardId: 'hero', sequence: 1 });
    expect(state.notices.hero).toBe('Earlier notes saved. Newer notes still need syncing.');
    expect(state.notices.detail).toBeUndefined();
    state = critiqueDraft(state, { type: 'edit', cardId: 'detail', notes: 'Detail' });
    state = critiqueDraft(state, { type: 'notice', generation: state.generation, cardId: 'detail', message: '' });
    state = critiqueDraft(state, { type: 'saved', generation: state.generation, cardId: 'detail', sequence: 1 });
    expect(state.notices.detail).toBe('✓ Directives saved to .creative/review-directives.json');
    expect(state.notices.hero).toBe('Earlier notes saved. Newer notes still need syncing.');
    state = critiqueDraft(state, { type: 'edit', cardId: 'hero', notes: 'Another edit' });
    expect(state.notices.hero).toBe('');
    expect(state.notices.detail).toBe('✓ Directives saved to .creative/review-directives.json');
    const inactive = critiqueDraft(state, { type: 'invalidate' });
    expect(critiqueDraft(inactive, { type: 'notice', generation: state.generation,
      cardId: 'hero', message: 'Stale clipboard callback' })).toBe(inactive);
  });
  it('reports newer unsaved edits after a pending save completes, then confirms the latest save', () => {
    let state = started();
    state = critiqueDraft(state, { type: 'edit', cardId: 'hero', notes: 'Submitted' });
    state = critiqueDraft(state, { type: 'edit', cardId: 'hero', notes: 'Newer' });
    state = critiqueDraft(state, { type: 'saved', generation: state.generation, cardId: 'hero', sequence: 1 });
    expect(critiqueSaveNotice(state, 'hero')).toBe('Earlier notes saved. Newer notes still need syncing.');
    state = critiqueDraft(state, { type: 'saved', generation: state.generation, cardId: 'hero', sequence: 2 });
    state = critiqueDraft(state, { type: 'edit', cardId: 'detail', notes: 'Independent' });
    expect(critiqueSaveNotice(state, 'hero')).toBe('✓ Directives saved to .creative/review-directives.json');
  });
  it.each(['typed', ''])('preserves touched notes %j against delayed GET and hydrates independent cards', notes => {
    let state = started();
    state = critiqueDraft(state, { type: 'edit', cardId: 'hero', notes });
    state = critiqueDraft(state, { type: 'loaded', generation: state.generation, notes: { hero: 'Old', detail: 'Remote detail' } });
    expect(state.cards.hero).toMatchObject({ notes, dirty: true, touched: true, sequence: 1 });
    expect(state.cards.detail).toMatchObject({ notes: 'Remote detail', dirty: false, touched: false });
  });
  it('preserves touched state after save so delayed GET cannot restore stale notes', () => {
    let state = started();
    state = critiqueDraft(state, { type: 'edit', cardId: 'hero', notes: 'Saved edit' });
    state = critiqueDraft(state, { type: 'saved', generation: state.generation, cardId: 'hero', sequence: 1 });
    expect(state.cards.hero.dirty).toBe(false);
    state = critiqueDraft(state, { type: 'loaded', generation: state.generation, notes: { hero: 'Old' } });
    expect(state.cards.hero).toMatchObject({ notes: 'Saved edit', touched: true, dirty: false });
  });
  it.each(['Changed', 'Original'])('keeps an edit during save dirty even when its text is %s', notes => {
    let state = started();
    state = critiqueDraft(state, { type: 'edit', cardId: 'hero', notes: 'Original' });
    const sequence = state.cards.hero.sequence;
    state = critiqueDraft(state, { type: 'edit', cardId: 'hero', notes });
    state = critiqueDraft(state, { type: 'saved', generation: state.generation, cardId: 'hero', sequence });
    expect(state.cards.hero).toMatchObject({ notes, dirty: true, sequence: 2 });
  });
  it('saves cards independently and leaves failures unchanged', () => {
    let state = started();
    state = critiqueDraft(state, { type: 'edit', cardId: 'hero', notes: 'Hero' });
    state = critiqueDraft(state, { type: 'edit', cardId: 'detail', notes: 'Detail' });
    expect(critiqueDraft(state, { type: 'failed', generation: state.generation })).toBe(state);
    state = critiqueDraft(state, { type: 'saved', generation: state.generation, cardId: 'hero', sequence: 1 });
    expect(state.cards.hero.dirty).toBe(false);
    expect(state.cards.detail.dirty).toBe(true);
  });
  it('ignores loads and saves after unmount and across StrictMode effect restarts', () => {
    let state = started();
    const generation = state.generation;
    state = critiqueDraft(state, { type: 'edit', cardId: 'hero', notes: 'Local' });
    state = critiqueDraft(state, { type: 'invalidate' });
    expect(currentCritiqueSession(state, generation)).toBe(false);
    expect(critiqueDraft(state, { type: 'loaded', generation, notes: { hero: 'Old' } })).toBe(state);
    expect(critiqueDraft(state, { type: 'saved', generation, cardId: 'hero', sequence: 1 })).toBe(state);
    state = critiqueDraft(state, { type: 'start' });
    expect(currentCritiqueSession(state, generation)).toBe(false);
    expect(critiqueDraft(state, { type: 'loaded', generation, notes: { hero: 'Old' } })).toBe(state);
    expect(critiqueDraft(state, { type: 'saved', generation, cardId: 'hero', sequence: 1 })).toBe(state);
    expect(currentCritiqueSession(state, state.generation)).toBe(true);
  });
});
