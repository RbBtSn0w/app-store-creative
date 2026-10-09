import { useEffect, useRef, useState } from 'react';
import { readHistory } from './historyRequest';
import { formatInventoryBytes } from './inventoryPresentation';
import { parseMediaBudget, type MediaBudget } from './mediaBudget';
export function MediaBudgetPanel() {
  const [candidate, setCandidate] = useState('');
  const [report, setReport] = useState<MediaBudget | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const generation = useRef(0);
  useEffect(() => () => { generation.current++; }, []);
  async function inspect() {
    const request = ++generation.current;
    setBusy(true); setReport(null); setError('');
    try {
      const query = candidate.trim() ? `?candidate_id=${encodeURIComponent(candidate.trim())}` : '';
      const result = parseMediaBudget(await readHistory(`/api/storage/media-budget${query}`, 'media budget'), candidate.trim() || null);
      if (generation.current === request) setReport(result);
    } catch (failure) { if (generation.current === request) setError(failure instanceof Error ? failure.message : String(failure)); }
    finally { if (generation.current === request) setBusy(false); }
  }
  return <section className="m-6 p-5 border border-white/10 rounded-xl" aria-label="Media budget">
    <h2 className="font-semibold">Media budget</h2>
    <p className="text-sm text-white/60 my-3">Check retained archive payloads and optionally estimate one additional candidate revision. This advisory does not delete files.</p>
    <label>Candidate ID (optional)<input disabled={busy} value={candidate} onChange={event => { setCandidate(event.target.value); setReport(null); setError(''); }} /></label>
    <button disabled={busy} onClick={() => inspect()}>Check media budget</button>
    {busy && <p role="status">Checking archive payloads…</p>}
    {error && <p role="alert">{error}</p>}
    {report && <MediaBudgetReport report={report} />}
  </section>;
}

export function MediaBudgetReport({ report }: { report: MediaBudget }) {
  return <div className="space-y-2 mt-3">
      <p>{({ UNKNOWN: 'Total unknown', NOT_CONFIGURED: 'Budget not configured', OVER_BUDGET: 'Projected payload exceeds budget', WITHIN_BUDGET: 'Projected local payload within budget' } as Record<string, string>)[report.status]}</p>
      <dl>{[['Retained payload', report.current_payload_bytes], ['Observed payload', report.observed_payload_bytes], ['Additional candidate payload', report.candidate_payload_bytes], ['Projected payload', report.forecast_payload_bytes], ['Configured budget', report.configured_limit_bytes]].map(([label, amount]) => <div key={String(label)}><dt>{label}</dt><dd>{formatInventoryBytes(amount as number | null)}</dd></div>)}</dl>
      <p className="text-sm text-white/60">Each retained revision counts its materialized artifact copies. Metadata and shared disk blocks are excluded. Git history and remote storage usage are unknown.</p>
      {report.reason && <p role="alert">{report.reason}</p>}
      {!!report.unverified_deliveries.length && <ul>{report.unverified_deliveries.map(item => <li key={item.id}>{item.id}: {item.reason}</li>)}</ul>}
    </div>;
}
