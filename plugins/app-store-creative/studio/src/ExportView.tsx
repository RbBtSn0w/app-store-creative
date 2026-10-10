import { useEffect, useRef, useState } from 'react';
import { CardView } from './components/CardView';
import { resolveCard } from './project';
import { reviewCard } from './layoutReview';
import { requireConfiguredFont } from './fontReview';
import type { CreativeConfig, TargetDevice } from './types';

export async function waitForExport(work: Promise<void>, timeoutMs = 6000): Promise<void> {
  let timer: ReturnType<typeof setTimeout>;
  const timeout = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new Error('Images or fonts did not become ready')), timeoutMs);
  });
  try { await Promise.race([work, timeout]); }
  finally { clearTimeout(timer!); }
}

export function ExportView({ config, id, target, locale }: {
  config: CreativeConfig; id: string; target: TargetDevice; locale: string;
}) {
  const root = useRef<HTMLDivElement>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState('');
  const index = config.cards.findIndex(card => card.id === id);
  const card = index >= 0 ? resolveCard(config, config.cards[index], target, locale) : undefined;
  useEffect(() => {
    let active = true;
    setReady(false); setError('');
    async function settle() {
      if (!root.current || !card) throw new Error('Requested card does not exist');
      await document.fonts.ready;
      await requireConfiguredFont(config.theme.fontFamily);
      const images = Array.from(root.current.querySelectorAll('img'));
      await Promise.all(images.map(image => image.decode()));
      for (const image of images) if (!image.naturalWidth) throw new Error('Capture could not be decoded');
      const background = card.customBackground || config.theme.background;
      if (background?.type === 'image' && background.imageUrl) {
        const image = new Image(); image.src = background.imageUrl; await image.decode();
      }
      await new Promise(resolve => setTimeout(resolve, 100));
      const findings = reviewCard(root.current.querySelector('[data-card-id]')!);
      if (findings.length) throw new Error(findings.join('. '));
    }
    waitForExport(settle()).then(() => { if (active) setReady(true); })
      .catch(reason => { if (active) setError(String(reason.message || reason)); });
    return () => { active = false; };
  }, [config, id, target, locale]);
  return <div ref={root} data-export-ready={ready ? 'true' : 'false'} data-export-error={error || undefined}>
    {card ? <CardView card={card} index={index} totalCards={config.cards.length} target={target}
      theme={config.theme} locale={locale} isExport connected={config.connectedTrack} /> : <p>Card not found</p>}
  </div>;
}
