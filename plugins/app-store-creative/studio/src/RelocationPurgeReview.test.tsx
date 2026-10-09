import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it } from 'vitest';
import { RelocationPurgeReview } from './RelocationPurgeReview';
it('requires explicit review of the saved plan before resuming interrupted deletion', () => {
  const file = { path: '/tmp/retained', sha256: 'a'.repeat(64), size_bytes: 42 };
  const html = renderToStaticMarkup(<RelocationPurgeReview operationId="abc" savedPlan={{ id: 'def', files: [file], recovery: [{ ...file, path: '/tmp/recovery' }] }} onExecuted={() => undefined} />);
  expect(html).toContain('Review saved deletion plan to resume');
  expect(html).not.toContain('Create copy deletion plan');
  expect(html).not.toContain('Permanently delete reviewed copies');
});
