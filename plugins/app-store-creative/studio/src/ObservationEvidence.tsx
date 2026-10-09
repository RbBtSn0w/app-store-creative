import { useState } from 'react';
import { EvidencePersistence } from './EvidencePersistence';
export function ObservationEvidence() {
  const [id, setId] = useState(''); const [actor, setActor] = useState('');
  const [file, setFile] = useState<File | null>(null); const [reviewed, setReviewed] = useState(false);
  const [busy, setBusy] = useState(false); const [unresolved, setUnresolved] = useState(false);
  const [message, setMessage] = useState(''); const [error, setError] = useState('');
  const validFile = file !== null && file.size > 0 && file.size <= 20 * 1024 * 1024;
  const ready = !busy && !unresolved && reviewed && /^[0-9a-f]{32}$/.test(id.trim()) && Boolean(actor.trim()) && validFile;
  async function retain() {
    if (!ready || !file) return;
    setBusy(true); setReviewed(false); setError('');
    try {
      const encoded = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader(); reader.onerror = () => reject(new Error('Could not read selected evidence'));
        reader.onload = () => typeof reader.result === 'string' && reader.result.includes(';base64,')
          ? resolve(reader.result.split(';base64,')[1]) : reject(new Error('Could not encode selected evidence'));
        reader.readAsDataURL(file);
      });
      const response = await fetch('/api/publications/retain-evidence', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ observation_id: id.trim(), actor: actor.trim(), confirm: 'RETAIN', evidence_base64: encoded }) });
      const value = await response.json();
      if (!response.ok) throw new Error(value.error || 'Evidence retention failed');
      if (value.observation_id !== id.trim() || !/^[0-9a-f]{32}$/.test(value.id)) throw new Error('Unexpected retention response');
      setMessage('Private evidence retained. Evidence ID: ' + value.id + '. External persistence and independent retrieval are still required.');
    } catch (failure) { setError(String(failure)); setMessage('The request may have completed. Check saved records before another request. No automatic retry is performed.'); }
    finally { setBusy(false); setUnresolved(true); }
  }
  return <section className="mt-4 space-y-3"><h3>Keep original observation evidence</h3>
    <p>Choose the original receipt for a recorded observation. Its bytes must match the saved hash. This keeps a private local copy and does not approve uploading or verify remote media.</p>
    <label>Observation ID<input disabled={busy} value={id} onChange={event => { setId(event.target.value); setReviewed(false); }} /></label>
    <label>Recorded by<input disabled={busy} value={actor} onChange={event => { setActor(event.target.value); setReviewed(false); }} /></label>
    <label>Original receipt (up to 20 MiB)<input type="file" disabled={busy} onChange={event => { setFile(event.target.files?.[0] ?? null); setReviewed(false); }} /></label>
    {file && !validFile && <p role="alert">Choose a nonempty receipt up to 20 MiB.</p>}
    <label><input type="checkbox" disabled={busy || unresolved} checked={reviewed} onChange={event => setReviewed(event.target.checked)} />I checked the observation ID and original receipt.</label>
    <button disabled={!ready} onClick={() => void retain()}>Retain private evidence</button>
    {unresolved && <button disabled={busy} onClick={() => { setUnresolved(false); setReviewed(false); setMessage(''); setError(''); }}>Prepare another request after checking saved records</button>}
    {message && <p role="status">{message}</p>}{error && <p role="alert">{error}</p>}
    <EvidencePersistence />
  </section>;
}
