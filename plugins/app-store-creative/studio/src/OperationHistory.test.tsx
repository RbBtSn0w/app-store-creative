import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it } from 'vitest';
import { OperationHistory, OperationHistoryReport, parseOperationHistory, parseOperationJournals } from './OperationHistory';

const specimen = () => ({ status: 'FAIL', events: [{ event_id: 'event', record: 'artifacts/asset.json',
  status: 'INCOMPLETE', created_at: '2026-10-07T00:00:00Z', actor: 'producer', run_id: 'run' }],
  untracked_records: ['runs/missing.json'], duplicate_references: [], record_count: 2,
  coverage: ['runs', 'artifacts'], reason: 'Record commit evidence only' });

it('requires an explicit check before reporting commit health', () => {
  const html = renderToStaticMarkup(<OperationHistory />);
  expect(html).toContain('Check records');
  expect(html).not.toContain('Records verified');
});
it('shows incomplete writes and missing events without claiming remote readiness', () => {
  const html = renderToStaticMarkup(<OperationHistoryReport report={parseOperationHistory(specimen())} />);
  for (const text of ['Records need attention', 'Write incomplete', 'runs/missing.json', 'artifacts/asset.json',
    'Remote readiness and maintenance journals are checked separately']) expect(html).toContain(text);
});
it('rejects unknown statuses instead of presenting success', () => {
  expect(() => parseOperationHistory({ ...specimen(), status: 'READY' })).toThrow();
  expect(() => parseOperationHistory({ ...specimen(), events: [{ ...specimen().events[0], status: 'READY' }] })).toThrow();
});
it('keeps a superseded commit intent distinct from changed content', () => {
  const data = specimen(); data.events[0].status = 'NOT_COMMITTED';
  const html = renderToStaticMarkup(<OperationHistoryReport report={parseOperationHistory(data)} />);
  expect(html).toContain('Intent not committed'); expect(html).not.toContain('Content changed');
});

it('does not equate a recorded switch with verified execution', async () => {
  const { OperationJournalReport } = await import('./OperationHistory');
  const html = renderToStaticMarkup(<OperationJournalReport entries={[{record:'relocations/move/switched.json',
    created_at:'2026-10-07T00:00:00Z',operation:null,recorded_status:'SWITCHED'}]} />);
  expect(html).toContain('Recorded state: SWITCHED'); expect(html).toContain('not verify execution');
  expect(html).not.toContain('Records verified');
});

it('keeps explicitly abandoned missing commits distinct from committed records', () => {
  const data = specimen(); data.events[0].status = 'ABANDONED';
  const html = renderToStaticMarkup(<OperationHistoryReport report={parseOperationHistory(data)} />);
  expect(html).toContain('Missing commit explicitly abandoned'); expect(html).not.toContain('Record committed');
});

it('rejects incomplete journal entries before rendering', () => {
  const entry = {record:'maintenance/op.json', created_at:'2026-10-07T00:00:00Z', operation:null, recorded_status:'SWITCHED'};
  const response = {status:'OBSERVED', execution_verified:false, entries:[entry]};
  expect(parseOperationJournals(response)).toEqual([entry]);
  for (const invalid of [null, {}, {...entry, record:42}, {...entry, operation:{}}, {...entry, recorded_status:false}]) {
    expect(() => parseOperationJournals({...response, entries:[invalid]})).toThrow('Invalid operation journal');
  }
});
