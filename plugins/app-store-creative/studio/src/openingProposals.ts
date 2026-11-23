import type { CardConfig, OpeningProposal } from './types';

export type OpeningPair = [OpeningProposal, OpeningProposal];

export function defaultOpenings(cards: CardConfig[]): OpeningPair {
  const ids = cards.slice(0, 3).map(card => card.id);
  const last = ids.slice(-1);
  return [
    { audience: '', benefit: '', cardIds: ids },
    { audience: '', benefit: '', cardIds: [...last, ...ids.slice(0, -1)] },
  ];
}

export function orderedCards(cards: CardConfig[], proposal: OpeningProposal): CardConfig[] {
  const byId = new Map(cards.map(card => [card.id, card]));
  const opening: CardConfig[] = [];
  for (const id of proposal.cardIds) {
    const card = byId.get(id);
    if (card) {
      opening.push(card);
      byId.delete(id);
    }
  }
  return [...opening, ...byId.values()];
}
