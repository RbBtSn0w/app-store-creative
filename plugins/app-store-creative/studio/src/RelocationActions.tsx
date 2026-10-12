import { maintenanceRequest } from './maintenanceRequest';
import { useState } from 'react';
import { maintenanceAllowed } from './maintenanceState';

import { parseRelocationPlan, type RelocationPlan } from './relocationState';
export function RelocationActions({ onStorageChange }: { onStorageChange: () => void }) {
  const [roots, setRoots] = useState<Record<string, string>>({ workspaceRoot: '', objectRoot: '', releaseRoot: '', publicationRoot: '' });
  const [reverseId, setReverseId] = useState('');
  const [plan, setPlan] = useState<RelocationPlan | null>(null);
  const [actor, setActor] = useState(''); const [reason, setReason] = useState('');
  const [reviewed, setReviewed] = useState(false); const [confirmation, setConfirmation] = useState('');
  const [busy, setBusy] = useState(false); const [uncertain, setUncertain] = useState(false);
  const [message, setMessage] = useState(''); const [error, setError] = useState('');
  async function run(action: 'plan' | 'verify' | 'prepare' | 'switch', reverse = false) {
    if (action !== 'plan' && !plan) return;
    if (action === 'plan' && reverse && !/^[a-z0-9]+$/.test(reverseId)) return;
    if ((action === 'prepare' || action === 'switch') && (!maintenanceAllowed(busy, uncertain, reviewed, actor, reason) || confirmation !== action.toUpperCase())) return;
    if (action === 'switch') onStorageChange();
    setBusy(true); setError(''); setReviewed(false); setConfirmation('');
    try {
      const payload = action === 'plan' && reverse ? { id: reverseId } : action === 'plan' ? { storage: Object.fromEntries(Object.entries(roots).filter(([, value]) => value.trim()).map(([key, value]) => [key, value.trim()])) } : action === 'verify' ? { id: plan!.id } : { id: plan!.id, actor: actor.trim(), reason: reason.trim(), confirm: action.toUpperCase() };
      const value = await maintenanceRequest('/api/storage/' + action + ((action === 'plan' ? reverse : plan!.operation === 'reverse-relocation-plan') ? '-reverse-relocate' : '-relocate'), payload) as {status?:string};
      if (action === 'plan') {
        const parsed = parseRelocationPlan(value);
        setPlan(parsed); setMessage('Plan saved. Review every source, target and file before preparing copies.');
      } else {
        setMessage('Recorded result: ' + value.status + (action === 'switch' ? '. Reload Studio before editing the new saved configuration.' : '. Each execution rechecks the plan.'));
        if (action === 'switch') { setUncertain(true); setPlan(null); }
      }
    } catch (failure) { setError(String(failure)); setUncertain(true); setMessage('Check the saved operation ID in the status panel. The request may already have completed. Reload after resolving the operation; writes are not retried automatically.'); }
    finally { setBusy(false); }
  }
  const labels: Record<string, string> = { workspaceRoot: 'New working directory', objectRoot: 'New media directory', releaseRoot: 'New archive directory', publicationRoot: 'New publication directory' };
  return <section className="rounded-2xl border border-white/10 p-5 space-y-3">
    <h2 className="text-lg font-medium">Plan storage relocation</h2>
    <p>Paths start from the project unless absolute. Empty values use defaults. Planning does not move files. Preparation checks Git staging rules; switching changes the saved configuration and preserves source bytes.</p>
    {Object.entries(roots).map(([key, value]) => <label key={key}>{labels[key]}<input disabled={busy || uncertain} value={value} onChange={event => { setRoots(previous => ({ ...previous, [key]: event.target.value })); setPlan(null); setReviewed(false); }} /></label>)}
    <button disabled={busy || uncertain} onClick={() => void run('plan')}>Create relocation plan</button>
    <label>Activated relocation ID to reverse<input disabled={busy || uncertain} value={reverseId} onChange={event => { setReverseId(event.target.value); setPlan(null); setReviewed(false); }} /></label>
    <button disabled={busy || uncertain || !/^[a-z0-9]+$/.test(reverseId)} onClick={() => void run('plan', true)}>Create reverse relocation plan</button>
    {message && <p role="status">{message}</p>}{error && <p role="alert">{error}</p>}
    {plan && <div className="space-y-2">
      <p>{plan.operation === 'reverse-relocation-plan' ? 'Reverse plan ID: ' : 'Plan ID: '}<code>{plan.id}</code> · {plan.files.length} files · {plan.logical_bytes} bytes</p>
      <ul>{Object.entries(plan.from).map(([key, value]) => <li key={key}>{key}: {value} → {plan.to[key]}</li>)}</ul>
      <ul>{plan.files.map((file, index) => <li key={index}>{file.root}/{file.path} · {file.size_bytes} bytes · <code>{file.sha256}</code></li>)}</ul>
      <button disabled={busy || uncertain} onClick={() => void run('verify')}>Verify relocation plan</button>
      <label>Relocation operator<input value={actor} onChange={event => setActor(event.target.value)} /></label>
      <label>Relocation reason<input value={reason} onChange={event => setReason(event.target.value)} /></label>
      <label><input type="checkbox" checked={reviewed} onChange={event => setReviewed(event.target.checked)} />I reviewed all directories and files.</label>
      <label>Type PREPARE or SWITCH<input value={confirmation} onChange={event => setConfirmation(event.target.value)} /></label>
      <button disabled={!maintenanceAllowed(busy, uncertain, reviewed, actor, reason) || confirmation !== 'PREPARE'} onClick={() => void run('prepare')}>Prepare verified copies</button>
      <button disabled={!maintenanceAllowed(busy, uncertain, reviewed, actor, reason) || confirmation !== 'SWITCH'} onClick={() => void run('switch')}>Switch prepared directories</button>
    </div>}
  </section>;
}
