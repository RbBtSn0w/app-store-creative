import { maintenanceRequest as request } from './maintenanceRequest';
import { useState } from 'react';
import { readArtifactPolicy } from './artifactPolicy';
import { parseMaintenanceInspection, type MaintenanceInspection } from './maintenanceInspection';
import { maintenanceAllowed, purgeAllowed, parseMaintenance, type MaintenanceRecord } from './maintenanceState';


export function MaintenancePanel() {
  const [inspection, setInspection] = useState<MaintenanceInspection | null>(null);
  const [records, setRecords] = useState<MaintenanceRecord[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [selected, setSelected] = useState<MaintenanceRecord | null>(null);
  const [days, setDays] = useState('');
  const [quarantineDays, setQuarantineDays] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [actor, setActor] = useState('');
  const [reason, setReason] = useState('');
  const [reviewed, setReviewed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [unresolved, setUnresolved] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const select = (record: MaintenanceRecord | null) => { setInspection(null); setSelected(record); setReviewed(false); setConfirmation(''); };
  async function inspect(record: MaintenanceRecord) {
    setBusy(true); setError(''); setInspection(null);
    try { setInspection(parseMaintenanceInspection(await request('/api/history/maintenance/' + record.id), record.id)); }
    catch (failure) { setError(String(failure)); }
    finally { setBusy(false); }
  }
  async function loadPolicy() {
    setBusy(true); setError(''); select(null);
    try { const policy = await readArtifactPolicy(); setDays(String(policy.trialRetentionDays)); setQuarantineDays(String(policy.quarantineDays)); setMessage('Project retention settings loaded. Review before creating a plan.'); }
    catch (failure) { setError(String(failure)); }
    finally { setBusy(false); }
  }
  async function history(append = false) {
    setBusy(true); setError(''); select(null);
    try {
      const result = await request('/api/maintenance' + (append && cursor ? '?cursor=' + encodeURIComponent(cursor) : '')) as { maintenance?: unknown[]; next_cursor?: unknown };
      if (result.next_cursor !== null && typeof result.next_cursor !== 'string') throw new Error('Invalid maintenance cursor');
      if (!Array.isArray(result.maintenance)) throw new Error('Invalid maintenance history');
      const loaded = result.maintenance.map(parseMaintenance);
      setRecords(previous => append ? [...previous, ...loaded] : loaded);
      setCursor(result.next_cursor as string | null); setUnresolved(false);
      setMessage('Saved records loaded. Recorded status is not independent execution verification.');
    } catch (failure) { setError(String(failure)); setUnresolved(true); setRecords([]); setCursor(null); }
    finally { setBusy(false); }
  }
  async function plan() {
    setBusy(true); setError(''); select(null);
    try {
      const count = Number(days);
      if (!Number.isSafeInteger(count) || count < 0 || days.trim() === '') throw new Error('Enter nonnegative whole retention days');
      select(parseMaintenance(await request('/api/maintenance/plan', { retention_days: count })));
      setMessage('Plan saved. No objects have moved. Review the complete object list before confirming.');
    } catch (failure) { setError(String(failure)); setUnresolved(true); }
    finally { setBusy(false); }
  }
  async function planPurge(record: MaintenanceRecord) {
    setBusy(true); setError(''); select(null);
    try {
      const count = Number(quarantineDays);
      if (!Number.isSafeInteger(count) || count < 0 || quarantineDays.trim() === '') throw new Error('Enter nonnegative whole quarantine days');
      select(parseMaintenance(await request('/api/maintenance/plan-purge', { id: record.id, quarantine_days: count })));
      setMessage('Permanent deletion plan saved. Review all objects; deletion cannot be reversed.');
    } catch (failure) { setError(String(failure)); setUnresolved(true); }
    finally { setBusy(false); }
  }
  async function execute() {
    if (!selected || !maintenanceAllowed(busy, unresolved, reviewed, actor, reason)) return;
    const restore = selected.operation === 'quarantine';
    const purge = selected.operation === 'purge-plan';
    if (purge && !purgeAllowed(busy, unresolved, reviewed, actor, reason, confirmation)) return;
    setBusy(true); setError(''); setReviewed(false); setInspection(null);
    try {
      const result = await request(purge ? '/api/maintenance/purge' : restore ? '/api/maintenance/restore' : '/api/maintenance/quarantine', {
        id: selected.id, actor: actor.trim(), reason: reason.trim(), confirm: purge ? 'PURGE' : restore ? 'RESTORE' : 'QUARANTINE',
      }) as { id?: string; operation?: string; status?: string };
      if (purge) { select(null); setMessage(`Permanent deletion recorded for ${result.id}. Load saved records to review the outcome.`); }
      else if (restore) { select(null); setMessage(`Recovery recorded for ${result.id}. Check saved records before another operation.`); }
      else { select(parseMaintenance(result)); setMessage('Objects moved to recovery storage. Originals can be restored; no permanent deletion was requested.'); }
    } catch (failure) {
      setError(String(failure)); setUnresolved(true); select(null);
      setMessage('The request may have completed. Load saved records before retrying.');
    } finally { setBusy(false); }
  }
  const action = selected?.operation === 'purge-plan' ? 'Permanently delete reviewed objects' : selected?.operation === 'cleanup-plan' ? 'Move reviewed objects to recovery storage' : 'Restore reviewed objects';
  return <section className="rounded-2xl border border-white/10 p-5 space-y-3">
    <h2 className="text-lg font-medium">Storage maintenance</h2>
    <p className="text-sm text-slate-400">Create a retention plan, review objects, then explicitly move them to recovery storage. Current references are rechecked before execution.</p>
    <div className="flex gap-3 items-end">
      <button disabled={busy} onClick={() => void loadPolicy()}>Use project retention settings</button>
      <label>Retention days<input type="number" min="0" step="1" value={days} onChange={event => { setDays(event.target.value); select(null); }} /></label>
      <button disabled={busy || unresolved || !/^\d+$/.test(days)} onClick={() => void plan()}>Create plan</button>
      <label>Quarantine days<input type="number" min="0" step="1" value={quarantineDays} onChange={event => { setQuarantineDays(event.target.value); select(null); }} /></label>
      <button disabled={busy} onClick={() => void history()}>Load saved maintenance records</button>
    </div>
    {message && <p role="status">{message}</p>}{error && <p role="alert" className="text-red-300">{error}</p>}
    {records.length > 0 && <ul className="space-y-2">{records.map(record => <li key={record.id}>
      <button disabled={busy} onClick={() => void inspect(record)}>Check current execution</button>
      {record.operation} · {record.id.slice(0, 8)} · {record.recorded_status || 'no outcome recorded'} · {record.objects.length} objects
      {record.operation === 'quarantine' && record.recorded_status !== 'restored' && record.recorded_status !== 'purged' &&
        <span><button disabled={busy || unresolved} onClick={() => select(record)}>Review recovery</button> <button disabled={busy || unresolved || !/^\d+$/.test(quarantineDays)} onClick={() => void planPurge(record)}>Create permanent deletion plan</button></span>}
      {record.operation === 'purge-plan' && <button disabled={busy || unresolved} onClick={() => select(record)}>Review permanent deletion plan</button>}
    </li>)}</ul>}
    {inspection && <div role="status"><p>Execution check for {inspection.id}: {inspection.status} · {inspection.phase} · {inspection.execution_verified ? 'Verified for this scope' : 'Not verified'}</p><p>This read-only check does not authorize another operation.</p><ul>{inspection.errors.map((error, index) => <li key={index}>{error}</li>)}</ul></div>}
    {cursor && <button disabled={busy} onClick={() => void history(true)}>Load earlier maintenance records</button>}
    {selected && <div className="space-y-3">
      <h3>Review {selected.id}</h3><p>{selected.objects.length} objects · {selected.objects.reduce((total, object) => total + object.size_bytes, 0)} bytes</p>
      <ul>{selected.objects.map(object => <li key={object.sha256}><code>{object.sha256}</code> · {object.size_bytes} bytes</li>)}</ul>
      {selected.operation === 'purge-plan' && <div role="note"><p>Permanent deletion removes these recovery copies and cannot be undone. Current references and retention are rechecked before execution.</p><label>Type PURGE to confirm<input value={confirmation} onChange={event => setConfirmation(event.target.value)} /></label></div>}
      <label>Operator<input value={actor} onChange={event => setActor(event.target.value)} /></label>
      <label>Reason<input value={reason} onChange={event => setReason(event.target.value)} /></label>
      <label><input type="checkbox" checked={reviewed} onChange={event => setReviewed(event.target.checked)} />I reviewed this object list and authorize this operation.</label>
      <button disabled={!(selected.operation === 'purge-plan' ? purgeAllowed(busy, unresolved, reviewed, actor, reason, confirmation) : maintenanceAllowed(busy, unresolved, reviewed, actor, reason)) || (selected.operation === 'cleanup-plan' && selected.objects.length === 0)} onClick={() => void execute()}>{action}</button>
    </div>}
  </section>;
}
