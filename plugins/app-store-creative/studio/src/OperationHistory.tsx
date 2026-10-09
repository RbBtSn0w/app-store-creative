import { useEffect, useRef, useState } from 'react';
import { readHistory } from './historyRequest';

const labels = { COMMITTED: 'Record committed', INCOMPLETE: 'Write incomplete', CHANGED: 'Content changed',
  NOT_COMMITTED: 'Intent not committed', ABANDONED: 'Missing commit explicitly abandoned' } as const;
type Event = { event_id: string; record: string; status: keyof typeof labels; created_at: string; actor: string | null; run_id: string | null };
type Report = { status: 'PASS' | 'FAIL'; events: Event[]; untracked_records: string[];
  duplicate_references: string[]; record_count: number; coverage: string[]; reason: string };

export function parseOperationHistory(value: unknown): Report {
  if (!value || typeof value !== 'object') throw new Error('Invalid record verification response');
  const data = value as Report;
  const strings = (items: unknown): items is string[] => Array.isArray(items) && items.every(item => typeof item === 'string');
  if (!['PASS', 'FAIL'].includes(data.status) || !Array.isArray(data.events)
      || !strings(data.untracked_records) || !strings(data.duplicate_references) || !strings(data.coverage)
      || !Number.isInteger(data.record_count) || data.record_count < 0 || typeof data.reason !== 'string')
    throw new Error('Invalid record verification response');
  for (const event of data.events) {
    if (!event || !Object.hasOwn(labels, event.status) || typeof event.event_id !== 'string'
        || typeof event.record !== 'string' || typeof event.created_at !== 'string')
      throw new Error('Invalid commit event response');
  }
  return data;
}

export function OperationHistoryReport({ report }: { report: Report }) {
  return <div className="mt-4 space-y-3" aria-live="polite">
    <h3 className="font-semibold">{report.status === 'PASS' ? 'Records verified' : 'Records need attention'}</h3>
    <p>{report.record_count} records checked · {report.events.length} commit intents</p>
    <p className="text-sm text-white/60">Remote readiness and maintenance journals are checked separately.</p>
    <ul className="max-h-80 overflow-y-auto space-y-2" aria-label="Record commits">{report.events.map(event =>
      <li key={event.event_id} className="p-3 bg-white/5 rounded-lg">
        <p>{labels[event.status]}</p><p className="text-sm break-all">{event.record}</p>
        <p className="text-xs text-white/60">{new Date(event.created_at).toLocaleString()}{event.actor ? ` · ${event.actor}` : ''}</p>
      </li>)}</ul>
    {([['Records missing commit evidence', report.untracked_records], ['Duplicate commit references', report.duplicate_references]] as const)
      .map(([title, items]) => items.length > 0 && <div key={title} className="text-amber-200">
        <h4>{title}</h4><ul>{items.map(item => <li className="break-all" key={item}>{item}</li>)}</ul></div>)}
    <details className="text-sm text-white/60"><summary>Check scope</summary><p>{report.coverage.join(', ')}</p><p>{report.reason}</p></details>
  </div>;
}

type JournalEntry = { record: string; created_at: string; operation: string | null; recorded_status: string | null };
export function OperationJournalReport({ entries }: { entries: JournalEntry[] }) {
  return <div className="mt-4 space-y-3"><h3 className="font-semibold">Migration and maintenance journals</h3>
    <p className="text-sm text-white/60">These are saved operation facts. This list does not verify execution or authorize recovery and deletion.</p>
    {!entries.length && <p>No operation journal records observed.</p>}
    <ul className="max-h-80 overflow-y-auto space-y-2">{entries.map(entry => <li key={entry.record} className="p-3 bg-white/5 rounded-lg">
      <p>{entry.operation || 'Operation receipt'} · Recorded state: {entry.recorded_status || 'Not declared'}</p>
      <p className="text-xs text-white/60 break-all">{entry.record} · {new Date(entry.created_at).toLocaleString()}</p>
    </li>)}</ul>
  </div>;
}

export function OperationHistory() {
  const [report, setReport] = useState<Report | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [journals, setJournals] = useState<JournalEntry[] | null>(null);
  const generation = useRef(0);
  useEffect(() => () => { generation.current++; }, []);
  async function check() {
    const request = ++generation.current;
    setBusy(true); setError(''); setReport(null);
    try {
      const data = parseOperationHistory(await readHistory('/api/history', 'record verification'));
      if (request === generation.current) setReport(data);
    } catch (failure) { if (request === generation.current) setError((failure as Error).message); }
    finally { if (request === generation.current) setBusy(false); }
  }
  async function loadJournals() {
    const request = ++generation.current; setBusy(true); setError(''); setJournals(null);
    try {
      const data = await readHistory<{status: string; execution_verified: boolean; entries: JournalEntry[]}>('/api/history/operations', 'operation journals');
      if (data.status !== 'OBSERVED' || data.execution_verified !== false || !Array.isArray(data.entries))
        throw new Error('Invalid operation journal response');
      if (request === generation.current) setJournals(data.entries);
    } catch (failure) { if (request === generation.current) setError((failure as Error).message); }
    finally { if (request === generation.current) setBusy(false); }
  }
  return <section className="m-6 p-5 border border-white/10 rounded-xl">
    <div className="flex justify-between gap-4"><h2 className="font-semibold">Record verification</h2>
      <button disabled={busy} onClick={() => void check()}>Check records</button></div>
    <p className="text-sm text-white/60 mt-3">Check that saved production records match their commit evidence.</p>
    {busy && <p role="status">Checking records…</p>}
    {error && <p role="alert" className="text-amber-200">{error}</p>}
    {report && <OperationHistoryReport report={report} />}
    <button disabled={busy} onClick={() => void loadJournals()}>Load operation journals</button>
    {journals && <OperationJournalReport entries={journals} />}
  </section>;
}
