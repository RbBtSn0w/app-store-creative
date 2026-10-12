import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it } from 'vitest';
import { CandidatePreviewMedia } from './CandidatePreviewMedia';

it('lets the reviewer play the validated preview and inspect its poster', () => {
  const html = renderToStaticMarkup(<CandidatePreviewMedia candidateId="candidate 1" assets={{
    'preview/app_preview.mp4': {}, 'preview/poster.png': {},
  }} />);
  expect(html).toContain('<video');
  expect(html).toContain('controls=""');
  expect(html).toContain('/api/artifacts/candidate%201/preview/app_preview.mp4');
  expect(html).toContain('/api/artifacts/candidate%201/preview/poster.png');
  expect(html).toContain('App Preview poster');
});

it('does not offer media absent from the validated candidate', () => {
  const html = renderToStaticMarkup(<CandidatePreviewMedia candidateId="candidate" assets={{
    'en-US/mac_16_10/card.png': {},
  }} />);
  expect(html).toBe('');
});

it('allows reviewing a poster without inventing a playable preview', () => {
  const html = renderToStaticMarkup(<CandidatePreviewMedia candidateId="candidate" assets={{
    'preview/poster.png': {},
  }} />);
  expect(html).toContain('App Preview poster');
  expect(html).not.toContain('<video');
});
