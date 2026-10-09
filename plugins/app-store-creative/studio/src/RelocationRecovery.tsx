import { useState } from 'react';
import { maintenanceAllowed } from './maintenanceState';
export function RelocationRecovery({ onStorageChange }: { onStorageChange: () => void }) {
  const [id, setId] = useState(''); const [workspace, setWorkspace] = useState('');
  const [action, setAction] = useState('resume-relocate');
  const [actor, setActor] = useState(''); const [reason, setReason] = useState('');
  const [reviewed, setReviewed] = useState(false); const [confirmation, setConfirmation] = useState('');
  const [busy, setBusy] = useState(false); const [unresolved, setUnresolved] = useState(false);
  const [message, setMessage] = useState(''); const [error, setError] = useState('');
  const expected = action.startsWith('resume') ? 'RESUME' : 'ROLLBACK';
  const allowed = maintenanceAllowed(busy, unresolved, reviewed, actor, reason) && /^[a-z0-9]+$/.test(id) && workspace.trim().length > 0 && confirmation === expected;
  function invalidate() { setReviewed(false); setConfirmation(''); }
  async function execute() {
    if (!allowed) return;
    onStorageChange(); setBusy(true); invalidate(); setError('');
    try {
      const response = await fetch('/api/storage/' + action, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id, source_workspace: workspace, actor: actor.trim(), reason: reason.trim(), confirm: expected }) });
      const value = await response.json();
      if (!response.ok) throw new Error(value.error || 'Relocation recovery failed');
      setMessage('Recorded recovery result: ' + value.status + '. Check operation status, then reload the project before further writes.');
    } catch (failure) { setError(String(failure)); setMessage('The request may have completed. Check saved operation status and recovery evidence before retrying; do not change directories manually.'); }
    finally { setBusy(false); setUnresolved(true); }
  }
  return <section className="rounded-2xl border border-white/10 p-5 space-y-3">
    <h2 className="text-lg font-medium">Recover interrupted relocation</h2>
    <p>Use the original workspace saved before switching. Recovery verifies that workspace and configuration authority before writing. A completed switch requires a separate reverse plan.</p>
    <label>Recovery plan ID<input disabled={busy || unresolved} value={id} onChange={event => { setId(event.target.value); invalidate(); }} /></label>
    <label>Original source workspace<input disabled={busy || unresolved} value={workspace} onChange={event => { setWorkspace(event.target.value); invalidate(); }} /></label>
    <label>Recovery operation<select disabled={busy || unresolved} value={action} onChange={event => { setAction(event.target.value); invalidate(); }}><option value="resume-relocate">Resume forward switch</option><option value="rollback-relocate">Roll back interrupted forward switch</option><option value="resume-reverse-relocate">Resume reverse switch</option><option value="rollback-reverse-relocate">Roll back interrupted reverse switch</option></select></label>
    <label>Recovery operator<input value={actor} onChange={event => setActor(event.target.value)} /></label>
    <label>Recovery reason<input value={reason} onChange={event => setReason(event.target.value)} /></label>
    <label><input type="checkbox" checked={reviewed} onChange={event => setReviewed(event.target.checked)} />I reviewed the operation, original workspace and recovery direction.</label>
    <label>Type {expected}<input value={confirmation} onChange={event => setConfirmation(event.target.value)} /></label>
    <button disabled={!allowed} onClick={() => void execute()}>Execute reviewed recovery</button>
    {message && <p role="status">{message}</p>}{error && <p role="alert">{error}</p>}
  </section>;
}
