import { useState } from 'react';
import { readHistory } from './historyRequest';

type Change = { path: string; role: string; present: boolean; reasons: string[] };
type Comparison = { baseline_version: string; candidate_version: string; assets: Change[] };

export function CandidateChanges({ candidate, baseline }: { candidate: string; baseline: string }) {
  const [result, setResult] = useState<Comparison>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function compare() {
    setBusy(true); setError(''); setResult(undefined);
    try {
      setResult(await readHistory<Comparison>('/api/candidates/' + encodeURIComponent(candidate) +
        '/compare?baseline=' + encodeURIComponent(baseline), 'candidate comparison', 120000));
    } catch (failure) { setError(String(failure)); }
    finally { setBusy(false); }
  }
  function asset(row: Change) {
    return <li key={row.path} className="break-all">
      {row.present ? <a className="underline" target="_blank" rel="noreferrer"
        href={'/api/artifacts/' + encodeURIComponent(candidate) + '/' + row.path.split('/').map(encodeURIComponent).join('/')}>{row.path}</a> : row.path}
      {row.reasons.length > 0 && ' · ' + row.reasons.join(', ')}
    </li>;
  }
  const changed = result?.assets.filter(row => row.reasons.length);
  const same = result?.assets.filter(row => !row.reasons.length);
  return <section className="space-y-2">
    <button disabled={busy} onClick={() => void compare()}>{busy ? 'Comparing media…' : 'Compare with current candidate'}</button>
    {error && <p role="alert">{error}</p>}
    {result && changed && same && <div aria-live="polite">
      <h4>{result.baseline_version} → {result.candidate_version} · {changed.length} to review</h4>
      <ul>{changed.map(asset)}</ul>
      <details><summary>{same.length} matching media files</summary>
        <p>Matching files can still show an older app interface. Check screens affected by app changes.</p>
        <ul>{same.map(asset)}</ul>
      </details>
    </div>}
  </section>;
}
