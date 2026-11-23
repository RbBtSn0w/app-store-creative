import { useState } from 'react';
import { readHistory } from './historyRequest';

type Row = { path: string; present: boolean; reasons: string[]; copy_changes: { field: string; before: string | null; after: string | null }[] };
export function ScreenshotPlan({ baseline, onOpenCard }: { baseline: string; onOpenCard: (path: string) => void }) {
  const [rows, setRows] = useState<Row[]>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function plan() {
    setBusy(true); setError(''); setRows(undefined);
    try {
      const result = await readHistory<{ assets: Row[] }>('/api/deliveries/' + encodeURIComponent(baseline) +
        '/screenshot-plan', 'screenshot update plan', 120000);
      setRows(result.assets);
    } catch (failure) { setError(String(failure)); }
    finally { setBusy(false); }
  }
  const changes = rows?.filter(row => row.reasons.length);
  return <section className="space-y-2">
    <button disabled={busy} onClick={() => void plan()}>{busy ? 'Checking sources…' : 'Plan screenshot updates'}</button>
    {error && <p role="alert">{error}</p>}
    {changes && rows && <div aria-live="polite">
      <h4>{changes.length} placements to review</h4>
      <ul>{changes.map(row => <li key={row.path}>{row.present ? <button onClick={() => onOpenCard(row.path)}>{row.path}</button> : row.path}
        {' · ' + row.reasons.join(', ')}
        {row.copy_changes.map(change => <p key={change.field} className="text-sm">
          {change.field}: <del>{change.before || '∅'}</del> → <ins>{change.after || '∅'}</ins>
        </p>)}</li>)}</ul>
      <details><summary>{rows.length - changes.length} matching recipes and sources</summary>
        <p>Review screenshots of any interface changed in the app since capture.</p>
        {rows.filter(row => !row.reasons.length).map(row => <button key={row.path} onClick={() => onOpenCard(row.path)}>{row.path}</button>)}
      </details>
    </div>}
  </section>;
}
