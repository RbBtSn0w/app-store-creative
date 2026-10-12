import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it } from 'vitest';
import { StorageSettings } from './StorageSettings';
import { parseStoragePreview } from './storagePreview';
import { specimen } from './storagePreview.fixture';
import type { CreativeConfig } from './types';
const config = {storage:{workspaceRoot:'work'}} as CreativeConfig;
it('renders editable output roots without inferring a successful check', () => {
  const html = renderToStaticMarkup(<StorageSettings config={config} onChange={() => {}} onCheck={() => {}} />);
  for (const label of ['Working files', 'Media objects', 'Release archives', 'Publication records', 'Preview directories']) expect(html).toContain(label);
  expect(html).not.toContain('/product/work');
});
it('renders resolved paths, sources and migration requirement', () => {
  const report = parseStoragePreview({...specimen(), requires_relocation:true});
  const html = renderToStaticMarkup(<StorageSettings config={config} onChange={() => {}} onCheck={() => {}} report={report} />);
  expect(html).toContain('/product/work/objects'); expect(html).toContain('Derived from working directory');
  expect(html).toContain('migration'); expect(html).not.toContain('Ready to save');
});
