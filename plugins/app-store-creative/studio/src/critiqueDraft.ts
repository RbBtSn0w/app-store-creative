export interface CritiqueCardDraft {
  notes: string;
  dirty: boolean;
  sequence: number;
  touched: boolean;
}

export interface CritiqueDraftState {
  cards: Record<string, CritiqueCardDraft>;
  notices: Record<string, string>;
  generation: number;
  active: boolean;
}

export type CritiqueDraftAction =
  | { type: 'start' }
  | { type: 'invalidate' }
  | { type: 'edit'; cardId: string; notes: string }
  | { type: 'loaded'; generation: number; notes: Record<string, string> }
  | { type: 'saved'; generation: number; cardId: string; sequence: number }
  | { type: 'notice'; generation: number; cardId: string; message: string }
  | { type: 'failed'; generation: number };

export const initialCritiqueDraft = (): CritiqueDraftState => ({ cards: {}, notices: {}, generation: 0, active: false });

export function currentCritiqueSession(state: CritiqueDraftState, generation: number): boolean {
  return state.active && state.generation === generation;
}

export function critiqueSaveNotice(state: CritiqueDraftState, cardId: string): string {
  return state.cards[cardId]?.dirty
    ? 'Earlier notes saved. Newer notes still need syncing.'
    : '✓ Directives saved to .creative/review-directives.json';
}

export function critiqueDraft(state: CritiqueDraftState, action: CritiqueDraftAction): CritiqueDraftState {
  if (action.type === 'start') return { ...state, active: true, generation: state.generation + 1 };
  if (action.type === 'invalidate') return { ...state, active: false };
  if (action.type === 'edit') {
    const previous = state.cards[action.cardId];
    return { ...state, notices: { ...state.notices, [action.cardId]: '' }, cards: { ...state.cards, [action.cardId]: {
      notes: action.notes, dirty: true, touched: true, sequence: (previous?.sequence || 0) + 1,
    } } };
  }
  if (!currentCritiqueSession(state, action.generation)) return state;
  if (action.type === 'notice') {
    return { ...state, notices: { ...state.notices, [action.cardId]: action.message } };
  }
  if (action.type === 'loaded') {
    const cards = { ...state.cards };
    for (const [id, notes] of Object.entries(action.notes)) {
      if (!cards[id]?.touched) cards[id] = { notes, dirty: false, touched: false, sequence: 0 };
    }
    return { ...state, cards };
  }
  if (action.type === 'saved') {
    const card = state.cards[action.cardId];
    const next = card && card.sequence === action.sequence
      ? { ...state, cards: { ...state.cards, [action.cardId]: { ...card, dirty: false } } }
      : state;
    return { ...next, notices: { ...next.notices, [action.cardId]: critiqueSaveNotice(next, action.cardId) } };
  }
  return state;
}
