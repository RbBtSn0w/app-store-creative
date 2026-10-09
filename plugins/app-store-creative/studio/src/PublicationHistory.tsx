import { useEffect, useRef, useState } from 'react';
import { readHistory } from './historyRequest';
import { PublicationHandoff } from './PublicationHandoff';

type Plan = { id: string; created_at: string; delivery_id: string; target: { app_id: string; version_id: string; platform: string } };
type Custody = { records: { evidence_id: string; observation_id: string; producer_succeeded: boolean }[]; versions: { id: string; reference: { backend: string; version: string } }[]; errors: string[] };
type Detail = { evidence_custody?: Custody; status: string; remote_verified: boolean; archive_verified?: boolean; retrieval_verified?: boolean;
  upload_approval?: string; gates: { artifact_id: string; gate: string; status: string }[] };
const gateLabel = (status: string) => ({ PASS: 'Passed', FAIL: 'Failed', CONFLICT: 'Conflicting evidence', UNKNOWN: 'Not verified' }[status] || 'Not verified');
export function PublicationReport({ detail }: { detail: Detail }) {
  const verified = detail.status === 'PASS' && detail.remote_verified === true;
  return <div className="mt-4 space-y-3" aria-live="polite">
    <h3 className="font-semibold">{verified ? 'Remote media verified' : ['FAIL', 'CONFLICT'].includes(detail.status) ? 'Needs attention' : 'Verification incomplete'}</h3>
    <p>Archive: {detail.archive_verified === true ? 'Verified' : 'Not verified'} · Archive retrieval: {detail.retrieval_verified === true ? 'Verified' : 'Not verified'}</p>
    <p>Upload approval: {detail.upload_approval === 'approved' ? 'Approved' : 'Pending'}</p>
    <ul className="space-y-2">{detail.gates.map((gate, index) => <li key={`${gate.artifact_id}/${gate.gate}/${index}`} className="p-3 bg-white/5 rounded-lg">
      <p>{gate.gate} · {gateLabel(gate.status)}</p><p className="text-xs text-white/60 break-all">{gate.artifact_id}</p>
    </li>)}</ul>
    {detail.evidence_custody && <section aria-label="Original receipt custody">
      <h3>Original receipt custody</h3>
      {detail.evidence_custody.errors.map((error, index) => <p role="alert" key={index}>{error}</p>)}
      <ul>{detail.evidence_custody.records.map(record => <li key={record.evidence_id}>
        Evidence: {record.evidence_id} · Observation: {record.observation_id} · {record.producer_succeeded ? 'Producer succeeded' : 'Producer incomplete'}
      </li>)}</ul>
      <ul>{detail.evidence_custody.versions.map(version => <li key={version.id}>
        Saved version: {version.id} · {version.reference.backend} · {version.reference.version}
      </li>)}</ul>
      <p>Review saved identities before repeating an uncertain request. A saved version does not prove current backend availability or remote media acceptance.</p>
    </section>}
    <p className="text-sm text-white/60">This reads saved observations. Request a fresh remote check through the ASC executor when evidence is missing or stale.</p>
  </div>;
}
export function PublicationHistory() {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [selected, setSelected] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const generation = useRef(0);
  useEffect(() => () => { generation.current++; }, []);
  async function load(more = false) {
    const request = ++generation.current; setBusy(true); setError(''); setDetail(null);
    if (!more) { setPlans([]); setCursor(null); setLoaded(false); setSelected(''); }
    try {
      const data = await readHistory<{publications: Plan[]; next_cursor: string | null}>('/api/publications?limit=20' + (more && cursor ? '&cursor=' + encodeURIComponent(cursor) : ''), 'publication plans');
      if (!Array.isArray(data.publications)) throw new Error('Invalid publication response');
      if (request === generation.current) { setPlans(current => more ? [...current, ...data.publications] : data.publications); setCursor(data.next_cursor); setLoaded(true); }
    } catch (failure) { if (request === generation.current) setError((failure as Error).message); }
    finally { if (request === generation.current) setBusy(false); }
  }
  async function inspect(id: string) {
    const request = ++generation.current; setBusy(true); setError(''); setDetail(null); setSelected(id);
    try {
      const data = await readHistory<Detail>('/api/publications/' + encodeURIComponent(id), 'publication verification');
      if (!Array.isArray(data.gates)) throw new Error('Invalid publication status response');
      if (request === generation.current) setDetail(data);
    } catch (failure) { if (request === generation.current) setError((failure as Error).message); }
    finally { if (request === generation.current) setBusy(false); }
  }
  return <section className="m-6 p-5 border border-white/10 rounded-xl">
    <div className="flex justify-between gap-4"><h2 className="font-semibold">Publication verification</h2>
      <button disabled={busy} onClick={() => void load()}>Load publication plans</button></div>
    <p className="text-sm text-white/60 my-3">Review independent upload, processing, playback and poster gates. This panel does not upload media.</p>
    {busy && <p role="status">Checking publication…</p>}{error && <p role="alert" className="text-amber-200">{error}</p>}
    {loaded && !plans.length && !busy && <p>No publication plans yet.</p>}
    <ul className="space-y-2 max-h-64 overflow-y-auto">{plans.map(plan => <li key={plan.id}>
      <button disabled={busy} aria-pressed={selected === plan.id} onClick={() => void inspect(plan.id)} className="w-full text-left">
        {plan.target.platform} · {plan.target.app_id} · {new Date(plan.created_at).toLocaleString()} · {plan.id.slice(0, 8)}
      </button></li>)}</ul>
    {cursor && <button disabled={busy} onClick={() => void load(true)}>Load earlier plans</button>}
    {detail && <><PublicationReport detail={detail} /><PublicationHandoff key={selected} id={selected} onSaved={() => void inspect(selected)} /><button disabled={busy} onClick={() => void inspect(selected)}>Check saved evidence again</button></>}
  </section>;
}
