import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it } from 'vitest';
import { CandidateApproval } from './CandidateApproval';
it('requires validation before offering approval or sealing', () => {
  const html = renderToStaticMarkup(<CandidateApproval candidateId="candidate" />);
  expect(html).toContain('Validate candidate'); expect(html).toContain('Candidate: candidate');
  expect(html).not.toContain('Record design approval'); expect(html).not.toContain('Seal release archive');
  expect(html).toContain('does not authorize upload');
});
