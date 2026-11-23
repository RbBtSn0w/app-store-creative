import { expect, it } from 'vitest';
import { defaultOpenings, orderedCards } from './openingProposals';

const cards = ['history', 'search', 'paste', 'share'].map(id => ({ id, headline: id }));
it('reopens two saved choices after applying one, retaining the rest of the deck', () => {
  const choices = defaultOpenings(cards);
  choices[1] = { audience: 'Writers', benefit: 'Reuse a reply', cardIds: ['share', 'paste', 'search'] };
  const saved = JSON.parse(JSON.stringify(choices));
  const applied = orderedCards(cards, saved[1]);
  expect(applied.map(card => card.id)).toEqual(['share', 'paste', 'search', 'history']);
  expect(orderedCards(applied, saved[0])).toEqual(cards);
  expect(saved[1].benefit).toBe('Reuse a reply');
});
it('keeps remaining real cards available when a draft references a removed capture', () => {
  expect(orderedCards(cards, { audience: '', benefit: '', cardIds: ['missing', 'search'] })
    .map(card => card.id)).toEqual(['search', 'history', 'paste', 'share']);
});
