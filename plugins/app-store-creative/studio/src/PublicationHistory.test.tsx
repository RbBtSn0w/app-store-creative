import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it } from 'vitest';
import { PublicationHistory, PublicationReport, parsePublicationPlans } from './PublicationHistory';
it('does not claim remote readiness before a check', () => {
  const html = renderToStaticMarkup(<PublicationHistory />);
  expect(html).toContain('Load publication plans'); expect(html).not.toContain('Remote media verified');
});
it('presents processing and poster failure as independent gates', () => {
  const html = renderToStaticMarkup(<PublicationReport detail={{ status: 'FAIL', remote_verified: false,
    archive_verified: true, retrieval_verified: true, upload_approval: 'approved',
    gates: [{ artifact_id: 'video', gate: 'processing', status: 'PASS' }, { artifact_id: 'video', gate: 'poster', status: 'FAIL' }] }} />);
  for (const text of ['Needs attention', 'processing', 'poster', 'Passed', 'Failed']) expect(html).toContain(text);
  expect(html).not.toContain('Remote media verified');
});
it('requires an explicit verified flag before displaying completion', () => {
  const html = renderToStaticMarkup(<PublicationReport detail={{status:'PASS',remote_verified:false,gates:[]}} />);
  expect(html).toContain('Verification incomplete'); expect(html).not.toContain('Remote media verified');
});

it('shows saved receipt identities without claiming remote success', () => {
  const html = renderToStaticMarkup(<PublicationReport detail={{status:'UNKNOWN',remote_verified:false,gates:[],
    evidence_custody:{records:[{evidence_id:'receipt-id',observation_id:'observation-id',producer_succeeded:false}],versions:[],errors:[]}}} />);
  for (const text of ['Original receipt custody','receipt-id','observation-id','Producer incomplete']) expect(html).toContain(text);
  expect(html).not.toContain('Remote media verified');
});

it('rejects malformed publication rows before rendering', () => {
  for (const row of [null, {}, { id: 1 }, { id: 'plan', created_at: 'invalid', delivery_id: 'delivery', target: {} }]) {
    expect(() => parsePublicationPlans({ publications: [row], next_cursor: null })).toThrow('Invalid publication');
  }
  const row = { id: 'plan', created_at: '2026-10-13T00:00:00Z', delivery_id: 'delivery', target: { app_id: 'app', version_id: 'version', platform: 'MAC_OS' } };
  expect(parsePublicationPlans({ publications: [row], next_cursor: null }).publications).toEqual([row]);
});
