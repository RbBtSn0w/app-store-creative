import { useState } from 'react';
import { maintenanceAllowed } from './maintenanceState';
import { parseHandoffPreview, type HandoffPreview } from './publicationHandoffState';
export function PublicationHandoff({ id, onSaved }: { id: string; onSaved: () => void }) {
  const [preview, setPreview] = useState<HandoffPreview | null>(null);
  const [actor, setActor] = useState(''); const [authorization, setAuthorization] = useState('');
  const [reviewed, setReviewed] = useState(false); const [busy, setBusy] = useState(false); const [unresolved, setUnresolved] = useState(false);
  const [message, setMessage] = useState(''); const [error, setError] = useState('');
  async function load() {
    setBusy(true); setError(''); setPreview(null); setReviewed(false);
    try {
      const response = await fetch('/api/publication-handoff/' + encodeURIComponent(id), { cache: 'no-store' });
      const value = await response.json();
      if (!response.ok) throw new Error(value.error || 'Handoff review failed');
      setPreview(parseHandoffPreview(value, id)); setUnresolved(false); setMessage('Review loaded. No upload has been performed.');
    } catch (failure) { setError(String(failure)); setUnresolved(true); }
    finally { setBusy(false); }
  }
  async function execute(approve: boolean) {
    if (!preview || !maintenanceAllowed(busy, unresolved, reviewed, approve ? actor : 'export', approve ? authorization : 'export')) return;
    setBusy(true); setReviewed(false); setError('');
    try {
      const response = await fetch(approve ? '/api/publications/approve-upload' : '/api/publications/export', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(approve ? { publication_id: id, actor: actor.trim(), authorization_reference: authorization.trim(), confirm: 'UPLOAD' } : { publication_id: id, confirm: 'EXPORT' }) });
      const value = await response.json();
      if (!response.ok) throw new Error(value.error || 'Publication coordination failed');
      setMessage(approve ? 'Upload approval recorded for this plan. Reload review before exporting.' : 'Local handoff exported. Upload approval: ' + value.upload_approval + '. ASC must execute and verify the upload separately.');
      setPreview(null); setUnresolved(true);
      onSaved();
    } catch (failure) { setError(String(failure)); setUnresolved(true); setPreview(null); setMessage('The request may have completed. Reload saved review before retrying; writes are not retried automatically.'); }
    finally { setBusy(false); }
  }
  return <div className="mt-4 space-y-3">
    <h3>ASC handoff review</h3><button disabled={busy} onClick={() => void load()}>Load bound upload plan</button>
    {message && <p role="status">{message}</p>}{error && <p role="alert">{error}</p>}
    {preview && <><p>Plan SHA-256: <code>{preview.plan_sha256}</code> · Upload approval: {preview.upload_approval}</p>
      <ul>{Object.entries(preview.handoff.target).map(([key, value]) => <li key={key}>{key}: {value}</li>)}</ul>
      <ul>{preview.handoff.assets.map(item => <li key={item.artifact_id}>{item.role} · {item.path} · <code>{item.sha256}</code></li>)}</ul>
      <label>Approving person<input value={actor} onChange={event => setActor(event.target.value)} /></label>
      <label>Human authorization reference<input value={authorization} onChange={event => setAuthorization(event.target.value)} /></label>
      <label><input type="checkbox" checked={reviewed} onChange={event => setReviewed(event.target.checked)} />I reviewed this plan, target and complete asset list.</label>
      <button disabled={!maintenanceAllowed(busy, unresolved, reviewed, actor, authorization)} onClick={() => void execute(true)}>Approve upload for this plan</button>
      <button disabled={busy || unresolved || !reviewed} onClick={() => void execute(false)}>Export local ASC handoff</button>
      <p>Export creates local files only. Pending approval does not authorize uploading; the official ASC plugin performs remote actions.</p></>}
  </div>;
}
