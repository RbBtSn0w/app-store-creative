import { maintenanceRequest } from './maintenanceRequest';
import { useState } from 'react';
import { parsePurgePlan, type PurgePlan } from './relocationPurgeState';
import { RelocationPurgeReview } from './RelocationPurgeReview';
import { maintenanceAllowed } from './maintenanceState';
import { copyDispositionAllowed } from './relocationMaintenanceState';

type ObservedFile = { path: string; sha256: string; size_bytes: number };
type Observation = { purge_plan?: PurgePlan; files: ObservedFile[]; id: string; path: string; phase: string; status: string; expected_file_count: number; expected_logical_bytes: number; source_removal_executed: boolean | null };
export function RelocationMaintenanceHistory() {
  const [rows, setRows] = useState<Observation[]>([]);
  const [errors, setErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(false); const [message, setMessage] = useState('');
  const [selected, setSelected] = useState(''); const [action, setAction] = useState('commit');
  const [actor, setActor] = useState(''); const [reason, setReason] = useState('');
  const [reviewed, setReviewed] = useState(false); const [confirmation, setConfirmation] = useState('');
  async function load() {
    setSelected(''); setReviewed(false); setConfirmation('');
    setBusy(true); setRows([]); setErrors([]); setMessage('Checking retained preparation records…');
    try {
      const value = await maintenanceRequest('/api/relocation-maintenance') as {cleanup_executed: boolean; operations: Observation[]; unverified_operations: {id:string; reason:string}[]};
      if (value.cleanup_executed !== false || !Array.isArray(value.operations) || !Array.isArray(value.unverified_operations)) throw new Error('Invalid maintenance observations');
      const ids = new Set<string>();
      for (const row of value.operations) {
        if (!row || typeof row.id !== 'string' || !/^[a-z0-9]+$/.test(row.id) || ids.has(row.id) || typeof row.path !== 'string' || typeof row.phase !== 'string' || typeof row.status !== 'string' || !Number.isSafeInteger(row.expected_file_count) || row.expected_file_count < 0 || !Number.isSafeInteger(row.expected_logical_bytes) || row.expected_logical_bytes < 0 || ![true, false, null].includes(row.source_removal_executed)) throw new Error('Invalid preparation observation');
        if (!Array.isArray(row.files) || row.files.length !== row.expected_file_count) throw new Error('Incomplete saved file list');
        const paths = new Set<string>();
        for (const file of row.files) {
          if (!file || typeof file.path !== 'string' || !file.path.trim() || paths.has(file.path) || typeof file.sha256 !== 'string' || !/^[0-9a-f]{64}$/.test(file.sha256) || !Number.isSafeInteger(file.size_bytes) || file.size_bytes < 0) throw new Error('Invalid saved file identity');
          paths.add(file.path);
        }
        if (row.phase === 'PURGING' || row.phase === 'PURGED') parsePurgePlan(row.purge_plan, row.id);
        ids.add(row.id);
      }
      for (const row of value.unverified_operations) if (!row || typeof row.id !== 'string' || typeof row.reason !== 'string') throw new Error('Invalid unverified observation');
      setRows(value.operations); setErrors(value.unverified_operations.map((row: { id: string; reason: string }) => row.id + ': ' + row.reason));
      setMessage('Saved observations loaded. This check does not authorize source removal.');
    } catch (failure) { setMessage(String(failure)); }
    finally { setBusy(false); }
  }
  const current = rows.find(row => row.id === selected);
  const phaseAllowed = !!current && copyDispositionAllowed(current.phase, current.status, action);
  async function execute() {
    if (!current || !phaseAllowed || errors.length || confirmation !== action.toUpperCase() || !maintenanceAllowed(busy, false, reviewed, actor, reason)) return;
    const operationId = current.id;
    setBusy(true); setRows([]); setSelected(''); setReviewed(false); setConfirmation('');
    try {
      await maintenanceRequest('/api/relocation-maintenance/' + action, { id: operationId, actor: actor.trim(), reason: reason.trim(), confirm: action.toUpperCase() });
      setMessage('Operation recorded. Reload saved observations before continuing.');
    } catch (failure) { setMessage(String(failure) + '. The request may have completed. Reload saved observations before retrying.'); }
    finally { setBusy(false); }
  }
  return <section aria-label="Saved copy maintenance">
    <h3>Saved copy maintenance</h3>
    <button disabled={busy} onClick={() => void load()}>Check saved copy operations</button>
    <ul>{rows.map(row => <li key={row.id}><button disabled={busy} onClick={() => { setSelected(row.id); setReviewed(false); setConfirmation(''); }}>{row.id}</button> · {row.phase} · {row.status} · {row.expected_file_count} files · {row.expected_logical_bytes} bytes · {row.path}<p>Source removal: {row.source_removal_executed === null ? 'Unknown' : row.source_removal_executed ? 'Executed' : 'Not executed'}</p></li>)}</ul>
    {current && <div>
      <p>Selected saved operation: <code>{current.id}</code>. The core rechecks source identity and recovery copies before writing.</p>
      <ul>{current.files.map(file => <li key={file.path}>{file.path} · {file.size_bytes} bytes · <code>{file.sha256}</code></li>)}</ul>
      <label>Copy disposition<select value={action} onChange={event => { setAction(event.target.value); setReviewed(false); setConfirmation(''); }}><option value="commit">Quarantine originals</option><option value="restore">Restore or resume restoration</option><option value="resume">Resume interrupted preparation</option><option value="cancel">Cancel preparation and retain copies</option></select></label>
      <label>Disposition operator<input value={actor} onChange={event => { setActor(event.target.value); setReviewed(false); }} /></label>
      <label>Disposition reason<input value={reason} onChange={event => { setReason(event.target.value); setReviewed(false); }} /></label>
      <label><input type="checkbox" checked={reviewed} onChange={event => setReviewed(event.target.checked)} />I reviewed this saved operation, recovery copies and disposition.</label>
      <label>Type {action.toUpperCase()}<input value={confirmation} onChange={event => setConfirmation(event.target.value)} /></label>
      <button disabled={!phaseAllowed || errors.length > 0 || confirmation !== action.toUpperCase() || !maintenanceAllowed(busy, false, reviewed, actor, reason)} onClick={() => void execute()}>Execute reviewed copy disposition</button>
    </div>}
    {current && ((current.phase === 'QUARANTINED' && current.status === 'VERIFIED') || (current.phase === 'PURGING' && current.status === 'PURGING')) && !errors.length && <RelocationPurgeReview key={current.id} operationId={current.id} savedPlan={current.phase === 'PURGING' ? current.purge_plan : undefined} onExecuted={() => { setRows([]); setSelected(''); setReviewed(false); }} />}
    {errors.length > 0 && <div role="alert"><p>Unverified operations require investigation.</p><ul>{errors.map((error, index) => <li key={index}>{error}</li>)}</ul></div>}
    {message && <p role="status">{message}</p>}
  </section>;
}
