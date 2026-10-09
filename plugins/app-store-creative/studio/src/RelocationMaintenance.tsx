import { useState } from 'react';
import { readArtifactPolicy } from './artifactPolicy';
import { maintenanceAllowed } from './maintenanceState';
import { RelocationMaintenanceHistory } from './RelocationMaintenanceHistory';

import { parseCopyPlan, type CopyFile } from './relocationMaintenanceState';
export function RelocationMaintenance() {
  const [days, setDays] = useState('');
  const [files, setFiles] = useState<CopyFile[]>([]);
  const [id, setId] = useState(''); const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [actor, setActor] = useState(''); const [reason, setReason] = useState('');
  const [reviewed, setReviewed] = useState(false); const [confirmation, setConfirmation] = useState('');
  async function loadPolicy() {
    setBusy(true); setId(''); setFiles([]); setReviewed(false); setConfirmation('');
    try { const policy = await readArtifactPolicy(); setDays(String(policy.trialRetentionDays)); setMessage('Project retention settings loaded.'); }
    catch (failure) { setMessage(String(failure)); }
    finally { setBusy(false); }
  }
  async function plan() {
    setReviewed(false); setConfirmation('');
    setBusy(true); setFiles([]); setId(''); setMessage('Checking retained copies…');
    try {
      const response = await fetch('/api/relocation-maintenance/plan', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ retention_days: Number(days) }) });
      const value = await response.json();
      if (!response.ok) throw new Error(value.error || 'Copy retention planning failed');
      const saved = parseCopyPlan(value);
      setId(saved.id); setFiles(saved.files); setMessage('Plan saved. No copies were removed.');
    } catch (failure) { setMessage(String(failure)); }
    finally { setBusy(false); }
  }
  async function prepare() {
    if (!id || !files.some(file => file.decision === 'eligible') || confirmation !== 'PREPARE' || !maintenanceAllowed(busy, false, reviewed, actor, reason)) return;
    const planId = id;
    setBusy(true); setReviewed(false); setConfirmation(''); setId('');
    try {
      const response = await fetch('/api/relocation-maintenance/prepare', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: planId, actor: actor.trim(), reason: reason.trim(), confirm: 'PREPARE' }) });
      const value = await response.json();
      if (!response.ok) throw new Error(value.error || 'Copy quarantine preparation failed');
      if (typeof value.id !== 'string' || !/^[a-z0-9]+$/.test(value.id)) throw new Error('Invalid preparation identity');
      setMessage('Preparation saved: ' + value.id + '. Original copies remain until a separately reviewed commit. Check saved inventory before continuing.');
    } catch (failure) {
      setMessage(String(failure) + '. The request may have completed. Check saved inventory before retrying; writes are not automatically retried.');
    } finally { setBusy(false); setFiles([]); }
  }
  return <section className="space-y-3" aria-label="Relocation copy maintenance">
    <h2>Relocation copy maintenance</h2>
    <p>Review redundant objects and protected migration evidence before maintenance.</p>
    <button disabled={busy} onClick={() => void loadPolicy()}>Use project retention settings</button>
    <label>Copy retention days<input disabled={busy} value={days} onChange={event => { setDays(event.target.value); setReviewed(false); setConfirmation(''); setId(''); setFiles([]); setMessage(''); }} /></label>
    <button disabled={busy || !/^\d+$/.test(days) || !Number.isSafeInteger(Number(days))} onClick={() => void plan()}>Plan retained copies</button>
    {id && <p>Saved plan: <code>{id}</code></p>}
    <ul>{files.map(file => <li key={file.path}>{file.decision} · {file.reason} · {file.path} · {file.size_bytes} bytes · <code>{file.sha256}</code></li>)}</ul>
    {id && <>
      <label>Copy maintenance operator<input disabled={busy} value={actor} onChange={event => { setActor(event.target.value); setReviewed(false); }} /></label>
      <label>Copy maintenance reason<input disabled={busy} value={reason} onChange={event => { setReason(event.target.value); setReviewed(false); }} /></label>
      <label><input type="checkbox" checked={reviewed} onChange={event => setReviewed(event.target.checked)} />I reviewed the complete plan and independent recovery copies.</label>
      <label>Type PREPARE<input value={confirmation} onChange={event => setConfirmation(event.target.value)} /></label>
      <button disabled={!files.some(file => file.decision === 'eligible') || confirmation !== 'PREPARE' || !maintenanceAllowed(busy, false, reviewed, actor, reason)} onClick={() => void prepare()}>Prepare reviewed copy quarantine</button>
    </>}
    {message && <p role="status">{message}</p>}
    <RelocationMaintenanceHistory />
  </section>;
}
