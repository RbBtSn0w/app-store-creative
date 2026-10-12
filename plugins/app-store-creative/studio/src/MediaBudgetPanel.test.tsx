import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { MediaBudgetReport } from './MediaBudgetPanel';
import { parseMediaBudget } from './mediaBudget';
it('keeps incomplete archive totals unknown and exposes observed bytes as a separate measure', () => {
  const report = parseMediaBudget({ schema_version: 1, status: 'UNKNOWN', configured_limit_bytes: 100, current_payload_bytes: null, observed_payload_bytes: 40, candidate_id: null, candidate_payload_bytes: null, forecast_payload_bytes: null, unverified_deliveries: [{ id: 'delivery-1', reason: 'Archive unavailable' }], git_history_bytes: null, remote_storage_bytes: null, writes_performed: false, scope: 'Local payloads' });
  const html = renderToStaticMarkup(<MediaBudgetReport report={report} />);
  expect(html).toContain('Total unknown');
  expect(html).toContain('Retained payload</dt><dd>Not measured');
  expect(html).toContain('Observed payload</dt><dd>40 B');
  expect(html).toContain('Projected payload</dt><dd>Not measured');
  expect(html).toContain('Archive unavailable');
  expect(html).not.toContain('within budget');
  expect(html).not.toContain('<button');
});
