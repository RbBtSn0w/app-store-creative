import { useRef, useState } from 'react';
import { readHistory } from './historyRequest';

type Run = { id: string; created_at: string; target: { version?: string; platform?: string } };
type Page = { runs: Run[]; next_cursor: string | null };
type Detail = {
  attempts: { id: string; stage: string; outcome: { status: string; reason?: string } | null }[];
  artifacts: { id: string; role: string; logical_path?: string; partial: boolean;
    candidate_eligible: boolean; eligibility_errors: string[] }[];
};
export function RunHistory() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [selected, setSelected] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const generation = useRef(0);
  async function load(more = false) {
    const request = ++generation.current; setBusy(true); setError('');
    if (!more) { setDetail(null); setSelected(''); }
    try {
      const page = await readHistory<Page>('/api/runs?limit=20' + (more && cursor ? '&cursor=' + encodeURIComponent(cursor) : ''));
      if (request !== generation.current) return;
      setRuns(previous => more ? [...previous, ...page.runs.filter(run => !previous.some(item => item.id === run.id))] : page.runs);
      setCursor(page.next_cursor);
    } catch (failure) { if (request === generation.current) setError(String(failure)); }
    finally { if (request === generation.current) setBusy(false); }
  }
  async function inspect(run: Run) {
    const request = ++generation.current; setBusy(true); setError(''); setDetail(null); setSelected(run.id);
    try {
      const result = await readHistory<Detail>('/api/runs/' + encodeURIComponent(run.id));
      if (request === generation.current) setDetail(result);
    } catch (failure) { if (request === generation.current) setError(String(failure)); }
    finally { if (request === generation.current) setBusy(false); }
  }
  return <section className="m-6 p-5 border border-white/10 rounded-xl">
    <div className="flex justify-between gap-4"><h2 className="font-semibold">Production history</h2>
      <button disabled={busy} onClick={() => load()}>Load history</button></div>
    <p className="text-sm text-white/60 my-3">Review previous production attempts and retained assets. Selecting a history entry does not approve or publish it.</p>
    {busy && <p role="status">Loading history…</p>}
    {error && <p role="alert" className="text-amber-200">{error}</p>}
    <ul className="space-y-2">{runs.map(run => <li key={run.id}><button disabled={busy}
      aria-pressed={selected === run.id} onClick={() => inspect(run)}>
      {run.target.version || 'Unversioned'} · {run.target.platform || 'Production'} · {new Date(run.created_at).toLocaleString()}
    </button></li>)}</ul>
    {cursor && <button disabled={busy} onClick={() => load(true)}>Load earlier runs</button>}
    {detail && <div className="mt-4 space-y-3">
      <h3 className="font-semibold">Attempts</h3><ul>{detail.attempts.map(attempt => <li key={attempt.id}>
        {attempt.stage} · {attempt.outcome?.status || 'No terminal result'}{attempt.outcome?.reason && <p className="text-amber-200">{attempt.outcome.reason}</p>}
      </li>)}</ul>
      <h3 className="font-semibold">Retained assets</h3><ul>{detail.artifacts.map(artifact => <li key={artifact.id}>
        {artifact.logical_path || artifact.role} · {artifact.partial ? 'Partial output' : artifact.candidate_eligible ? 'Available for selection' : 'Unavailable for selection'}
        {artifact.eligibility_errors.map((finding, index) => <p className="text-amber-200" key={index}>{finding}</p>)}
      </li>)}</ul>
    </div>}
  </section>;
}
