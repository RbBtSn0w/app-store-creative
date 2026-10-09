import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { ArchivePolicySettings } from './ArchivePolicySettings';
it('leaves the archive choice undeclared during exploration', () => {
  const html = renderToStaticMarkup(<ArchivePolicySettings onChange={() => {}} />);
  expect(html).toContain('Not selected');
  expect(html).toContain('Choose before producing a release run');
  expect(html).not.toContain('Backend name');
});
it('exposes the portable backend name for an external declaration', () => {
  const html = renderToStaticMarkup(<ArchivePolicySettings policy={{ schema_version: 1, mediaMode: 'external', backend: 'team-media' }} onChange={() => {}} />);
  expect(html).toContain('Backend name');
  expect(html).toContain('team-media');
  expect(html).not.toContain('Backend path');
});
it('shows an explicit media budget without inventing one for exploration', () => {
  const html = renderToStaticMarkup(<ArchivePolicySettings onChange={() => {}} />);
  expect(html).toContain('Media budget (bytes)');
  expect(html).toContain('Leave empty for exploration');
});
