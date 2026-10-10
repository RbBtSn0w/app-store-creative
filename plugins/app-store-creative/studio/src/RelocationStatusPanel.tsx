import { readHistory } from './historyRequest';
import { useState } from 'react';
import { parseRelocatedObjects, type RelocatedObjects } from './relocatedObjects';

type RelocationStatus = {
  id: string; status: string; current_binding_writable: boolean;
  target_activation_status: string; recovery: string; errors: string[];
  target_activation_errors: string[]; media_integrity_verified: boolean;
};

export function RelocationStatusPanel() {
  const [objects, setObjects] = useState<RelocatedObjects | null>(null);
  const [id, setId] = useState('');
  const [result, setResult] = useState<RelocationStatus | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function inspectObjects() {
    setBusy(true); setObjects(null); setError('');
    try {
      if (!/^[a-z0-9]+$/.test(id)) throw new Error('Enter a saved relocation plan ID');
      const value = await readHistory('/api/storage/relocated-objects?id=' + encodeURIComponent(id), 'copied object inspection');
      setObjects(parseRelocatedObjects(value, id));
    } catch (failure) { setError(String(failure)); }
    finally { setBusy(false); }
  }
  async function check() {
    setBusy(true); setResult(null); setError('');
    try {
      if (!/^[a-z0-9]+$/.test(id)) throw new Error('Enter a saved relocation plan ID');
      const value = await readHistory<RelocationStatus>('/api/storage/relocation-status?id=' + encodeURIComponent(id), 'relocation status');
      if (value.id !== id || typeof value.status !== 'string' || typeof value.recovery !== 'string'
          || typeof value.current_binding_writable !== 'boolean' || typeof value.target_activation_status !== 'string'
          || typeof value.media_integrity_verified !== 'boolean' || !Array.isArray(value.errors)
          || !Array.isArray(value.target_activation_errors)
          || [...value.errors, ...value.target_activation_errors].some(item => typeof item !== 'string')) {
        throw new Error('Invalid relocation status response');
      }
      setResult(value);
    } catch (failure) { setError(String(failure)); }
    finally { setBusy(false); }
  }
  return <section className="rounded-2xl border border-white/10 p-5 space-y-3">
    <h2 className="text-lg font-medium">Storage relocation</h2>
    <p className="text-sm text-slate-400">Check a saved relocation plan. This query does not move files or change directories. Interrupted operations use the explicit recovery workflow.</p>
    <label>Relocation plan ID<input disabled={busy} value={id} onChange={event => { setId(event.target.value); setResult(null); setObjects(null); setError(''); }} /></label>
    <button disabled={busy || !id} onClick={() => void check()}>Check relocation status</button>
    <button disabled={busy || !id} onClick={() => void inspectObjects()}>Check copied object integrity</button>
    {objects && <div role="status"><p>Copied-object check for {objects.id}: {objects.status} · {objects.checked_files} files</p><p>{objects.scope}</p><p>Object integrity: {objects.object_integrity_verified ? 'Verified for this scope' : 'Not verified'}</p><ul>{objects.errors.map((item, index) => <li key={index}>{item}</li>)}</ul></div>}
    {error && <p role="alert" className="text-red-300">{error}</p>}
    {result && <div role="status" className="space-y-2">
      <p>Operation stage: {result.status}</p>
      <p>Current storage writable: {result.current_binding_writable ? 'Yes' : 'No'}</p>
      <p>Target activation: {result.target_activation_status}</p>
      <p>Recovery workflow: {result.recovery}</p>
      <p>Media integrity: {result.media_integrity_verified ? 'Verified' : 'Not verified by this query'}</p>
      {[...result.errors, ...result.target_activation_errors].length > 0 && <ul>{[...result.errors, ...result.target_activation_errors].map((item, index) => <li key={index}>{item}</li>)}</ul>}
    </div>}
  </section>;
}
