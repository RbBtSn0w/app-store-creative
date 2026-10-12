import { useState } from 'react';

export function EvidencePersistence() {
  const [id, setId] = useState('');
  const [backend, setBackend] = useState('');
  const [reviewed, setReviewed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [message, setMessage] = useState('');
  const ready = !busy && !submitted && reviewed && /^[0-9a-f]{32}$/.test(id.trim())
    && /^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$/.test(backend.trim());

  async function persist() {
    if (!ready) return;
    setBusy(true);
    setReviewed(false);
    try {
      const response = await fetch('/api/publications/persist-evidence', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ evidence_id: id.trim(), backend: backend.trim(), confirm: 'PERSIST' }),
      });
      const value = await response.json();
      if (!response.ok) throw new Error(value.error || 'Evidence persistence failed');
      if (value.retrieval_verified !== true || value.reference?.backend !== backend.trim()
          || !/^[0-9a-f]{32}$/.test(value.id)) throw new Error('Unexpected persistence response');
      setMessage('Evidence saved and independently read back. Version: ' + value.reference.version
        + '. This does not verify App Store media or the backend’s long-term availability.');
    } catch (error) {
      setMessage(String(error) + '. The request may have completed. Check saved records before retrying.');
    } finally {
      setBusy(false);
      setSubmitted(true);
    }
  }

  return <section className="mt-4 space-y-3">
    <h3>Persist original evidence</h3>
    <p>Use a backend already configured on this computer. Access paths stay private.</p>
    <label>Retained evidence ID<input disabled={busy} value={id} onChange={event => { setId(event.target.value); setReviewed(false); }} /></label>
    <label>Configured backend name<input disabled={busy} value={backend} onChange={event => { setBackend(event.target.value); setReviewed(false); }} /></label>
    <label><input type="checkbox" disabled={busy || submitted} checked={reviewed} onChange={event => setReviewed(event.target.checked)} />I reviewed the evidence and configured destination.</label>
    <button disabled={!ready} onClick={() => void persist()}>Persist private evidence</button>
    {message && <p role="status">{message}</p>}
    {submitted && <button disabled={busy} onClick={() => { setSubmitted(false); setReviewed(false); setMessage(''); }}>Prepare another persistence request after checking records</button>}
  </section>;
}
