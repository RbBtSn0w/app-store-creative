import { useRef, useState } from 'react';
import { readHistory } from './historyRequest';

type Run = { id: string; created_at: string; target: { version?: string; platform?: string } };
type Page = { runs: Run[]; next_cursor: string | null };
type Detail = {
  attempts: { id: string; stage: string; outcome: { status: string; reason?: string } | null }[];
  artifacts: { id: string; role: string; logical_path?: string; partial: boolean;
    candidate_eligible: boolean; eligibility_errors: string[] }[];
};
function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}
function text(value: unknown): value is string { return typeof value === 'string' && value.trim().length > 0; }
function optionalText(value: unknown): boolean { return value === undefined || typeof value === 'string'; }
export function parseRunPage(value: unknown): Page {
  if (!record(value) || !Array.isArray(value.runs) ||
      !(value.next_cursor === null || text(value.next_cursor)) ||
      !value.runs.every(run => record(run) && text(run.id) && text(run.created_at) &&
        record(run.target) && optionalText(run.target.version) && optionalText(run.target.platform))) {
    throw new Error('Production history response is incomplete.');
  }
  return value as Page;
}
export function parseRunDetail(value: unknown): Detail {
  if (!record(value) || !Array.isArray(value.attempts) || !Array.isArray(value.artifacts) ||
      !value.attempts.every(attempt => record(attempt) && text(attempt.id) && text(attempt.stage) &&
        (attempt.outcome === null || (record(attempt.outcome) && text(attempt.outcome.status) &&
          optionalText(attempt.outcome.reason)))) ||
      !value.artifacts.every(artifact => record(artifact) && text(artifact.id) && text(artifact.role) &&
        optionalText(artifact.logical_path) && typeof artifact.partial === 'boolean' &&
        typeof artifact.candidate_eligible === 'boolean' && Array.isArray(artifact.eligibility_errors) &&
        artifact.eligibility_errors.every(finding => typeof finding === 'string'))) {
    throw new Error('Production history detail is incomplete.');
  }
  return value as Detail;
}

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
      const page = parseRunPage(await readHistory<unknown>('/api/runs?limit=20' + (more && cursor ? '&cursor=' + encodeURIComponent(cursor) : '')));
      if (request !== generation.current) return;
      setRuns(previous => more ? [...previous, ...page.runs.filter(run => !previous.some(item => item.id === run.id))] : page.runs);
      setCursor(page.next_cursor);
    } catch (failure) { if (request === generation.current) setError(String(failure)); }
    finally { if (request === generation.current) setBusy(false); }
  }
  async function inspect(run: Run) {
    const request = ++generation.current; setBusy(true); setError(''); setDetail(null); setSelected(run.id);
    try {
      const result = parseRunDetail(await readHistory<unknown>('/api/runs/' + encodeURIComponent(run.id)));
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
