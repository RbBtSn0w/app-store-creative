import { useState } from 'react';
import { readArtifactPolicy } from './artifactPolicy';
import { purgeAllowed } from './maintenanceState';
import { parsePurgePlan, type PurgePlan } from './relocationPurgeState';
export function RelocationPurgeReview({ operationId, savedPlan, onExecuted }: { operationId: string; savedPlan?: PurgePlan; onExecuted: () => void }) {
  const [days, setDays] = useState(''); const [plan, setPlan] = useState<PurgePlan | null>(null);
  const [busy, setBusy] = useState(false); const [message, setMessage] = useState('');
  const [actor, setActor] = useState(''); const [reason, setReason] = useState('');
  const [reviewed, setReviewed] = useState(false); const [confirmation, setConfirmation] = useState('');
  function reviewSaved() {
    if (!savedPlan || busy) return;
    setPlan(parsePurgePlan(savedPlan, operationId)); setReviewed(false); setConfirmation('');
    setMessage('Saved interrupted deletion plan loaded. Review the complete original list before resuming.');
  }
  async function loadPolicy() {
    setBusy(true); setPlan(null); setReviewed(false); setConfirmation('');
    try { const policy = await readArtifactPolicy(); setDays(String(policy.quarantineDays)); setMessage('Project quarantine setting loaded.'); }
    catch (failure) { setMessage(String(failure)); }
    finally { setBusy(false); }
  }
  async function create() {
    setBusy(true); setPlan(null); setReviewed(false); setConfirmation('');
    try {
      const response = await fetch('/api/relocation-maintenance/plan-purge', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: operationId, quarantine_days: Number(days) }) });
      const value = await response.json();
      if (!response.ok) throw new Error(value.error || 'Purge planning failed');
      const saved = parsePurgePlan(value, operationId);
      setPlan(saved); setMessage('Plan saved. No files deleted.');
    } catch (failure) { setMessage(String(failure)); }
    finally { setBusy(false); }
  }
  async function execute() {
    if (!plan || !purgeAllowed(busy, false, reviewed, actor, reason, confirmation)) return;
    const id = plan.id; setBusy(true); setPlan(null); setReviewed(false); setConfirmation('');
    try {
      const response = await fetch('/api/relocation-maintenance/purge', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id, actor: actor.trim(), reason: reason.trim(), confirm: 'PURGE' }) });
      const value = await response.json();
      if (!response.ok) throw new Error(value.error || 'Permanent deletion failed');
      setMessage('Purge recorded. Reload saved observations.'); onExecuted();
    } catch (failure) { setMessage(String(failure) + '. Check saved observations before retrying; writes are not automatically retried.'); onExecuted(); }
    finally { setBusy(false); }
  }
  return <section aria-label="Permanent copy deletion">
    <h4>Permanent copy deletion</h4><p>This permanently removes the listed redundant copies. It cannot be undone through restoration.</p>
    {savedPlan ? <button disabled={busy} onClick={reviewSaved}>Review saved deletion plan to resume</button> : <><button disabled={busy} onClick={() => void loadPolicy()}>Use project retention settings</button><label>Copy quarantine days<input disabled={busy} value={days} onChange={event => { setDays(event.target.value); setPlan(null); setReviewed(false); setConfirmation(''); }} /></label>
    <button disabled={busy || !/^\d+$/.test(days) || !Number.isSafeInteger(Number(days))} onClick={() => void create()}>Create copy deletion plan</button></>}
    {plan && <><p>Deletion plan: <code>{plan.id}</code></p><h4>Copies to delete</h4><ul>{plan.files.map(file => <li key={file.path}>{file.path} · {file.size_bytes} bytes · <code>{file.sha256}</code></li>)}</ul><h4>Independent recovery objects retained</h4><ul>{plan.recovery.map(file => <li key={file.path}>{file.path} · {file.size_bytes} bytes · <code>{file.sha256}</code></li>)}</ul>
      <label>Deletion operator<input value={actor} onChange={event => { setActor(event.target.value); setReviewed(false); }} /></label><label>Deletion reason<input value={reason} onChange={event => { setReason(event.target.value); setReviewed(false); }} /></label>
      <label><input type="checkbox" checked={reviewed} onChange={event => setReviewed(event.target.checked)} />I reviewed and authorize permanent deletion of these exact copies.</label>
      <label>Type PURGE<input value={confirmation} onChange={event => setConfirmation(event.target.value)} /></label>
      <button disabled={!purgeAllowed(busy, false, reviewed, actor, reason, confirmation)} onClick={() => void execute()}>Permanently delete reviewed copies</button></>}
    {message && <p role="status">{message}</p>}
  </section>;
}
