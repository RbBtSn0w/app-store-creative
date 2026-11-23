import { useState } from 'react';
import { CardView } from './components/CardView';
import { defaultOpenings, orderedCards, type OpeningPair } from './openingProposals';
import { resolveCard } from './project';
import { getTargetScalingInfo, type CardConfig, type CreativeConfig, type OpeningProposal, type TargetDevice } from './types';

export function OpeningStory({ config, target, locale, disabled, onDraft, onApply }: {
  config: CreativeConfig; target: TargetDevice; locale: string; disabled: boolean; onDraft: (pair: OpeningPair) => void; onApply: (cards: CardConfig[], openings: OpeningPair) => void;
}) {
  const [open, setOpen] = useState(false);
  const [sequence, setSequence] = useState<0 | 1>(0);
  const drafts = config.studio?.openings ?? defaultOpenings(config.cards);
  const proposal = drafts[sequence];
  const cards = orderedCards(config.cards, proposal);
  const missing = proposal.cardIds.filter(id => !config.cards.some(card => card.id === id));
  function update(change: Partial<OpeningProposal>) {
    const pair: OpeningPair = [...drafts];
    pair[sequence] = { ...proposal, ...change };
    onDraft(pair);
  }
  const scale = 65 / getTargetScalingInfo(target).baseCanvasWidth;
  return <div>
    <button aria-expanded={open} onClick={() => setOpen(!open)}>Preview opening sequence</button>
    {open && <fieldset disabled={disabled} className="space-y-2 mt-2">
      <legend>Which benefit should people see first?</legend>
      <div className="flex gap-1">{['Opening A', 'Opening B'].map((name, index) =>
        <button key={name} type="button" aria-pressed={sequence === index} onClick={() => setSequence(index === 0 ? 0 : 1)}>{name}</button>)}</div>
      <label className="block text-xs">Audience<input value={proposal.audience}
        onChange={event => update({ audience: event.target.value })} /></label>
      <label className="block text-xs">Benefit to show first<input value={proposal.benefit}
        onChange={event => update({ benefit: event.target.value })} /></label>
      {missing.length > 0 && <p role="alert">Removed cards: {missing.join(', ')}. <button
        onClick={() => update({ cardIds: cards.slice(0, 3).map(card => card.id) })}>Use displayed cards</button></p>}
      <div className="flex gap-1" aria-label="Opening screenshots">{cards.slice(0, 3).map((card, index) =>
        <div key={card.id} style={{ zoom: scale }}><CardView card={resolveCard(config, card, target, locale)}
          index={index} totalCards={cards.length} connected={config.connectedTrack} target={target} theme={config.theme} isExport /></div>)}</div>
      {cards.slice(0, 3).map((card, index) => <label key={index} className="block text-xs">Position {index + 1}
        <select value={card.id} onChange={event => {
          const next = cards.map(item => item.id);
          const other = next.indexOf(event.target.value);
          [next[index], next[other]] = [next[other], next[index]];
          update({ cardIds: next.slice(0, 3) });
        }}>{config.cards.map(option => <option key={option.id} value={option.id}>
          {resolveCard(config, option, target, locale).headline || option.id}</option>)}</select>
      </label>)}
      <button disabled={missing.length > 0 || cards.every((card, index) => card.id === config.cards[index].id)}
        onClick={() => onApply(cards, drafts)}>Apply order to all languages</button>
    </fieldset>}
  </div>;
}
