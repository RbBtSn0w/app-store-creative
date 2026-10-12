import { useEffect, useState } from 'react';
import { readHistory } from './historyRequest';

async function action(path: string, data: unknown) {
  const response = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data), signal: AbortSignal.timeout(20000) });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || 'Action failed');
  return body;
}
export function CandidateApproval({ candidateId }: { candidateId: string }) {
  const [validation, setValidation] = useState<{id: string; status: string; errors?: string[]} | null>(null);
  const [approvalId, setApprovalId] = useState('');
  const [deliveryId, setDeliveryId] = useState('');
  const [actor, setActor] = useState('');
  const [reference, setReference] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [reviewReady, setReviewReady] = useState(false);
  async function recover() {
    setBusy(true); setError(''); setReviewReady(false); setConfirmed(false);
    try {
      const saved = await readHistory<{validation: typeof validation; approval_id: string | null; delivery_id: string | null}>(
        '/api/candidates/' + encodeURIComponent(candidateId) + '/review', 'saved candidate review');
      setValidation(saved.validation); setApprovalId(saved.approval_id || ''); setDeliveryId(saved.delivery_id || ''); setReviewReady(true);
    } catch (failure) { setError((failure as Error).message); }
    finally { setBusy(false); }
  }
  useEffect(() => { void recover(); }, [candidateId]);
  async function perform(kind: 'validate' | 'approve' | 'seal') {
    setBusy(true); setError('');
    try {
      if (kind === 'validate') {
        setValidation(null); setApprovalId(''); setDeliveryId(''); setConfirmed(false);
        setValidation(await action('/api/candidates/validate', {candidate_id: candidateId}));
      } else if (kind === 'approve' && validation?.status === 'PASS' && confirmed) {
        const result = await action('/api/approvals/design', {candidate_id:candidateId, validation_id:validation.id,
          actor:actor.trim(), authorization_reference:reference.trim(), confirm:'APPROVE'});
        setApprovalId(result.id); setConfirmed(false);
      } else if (kind === 'seal' && validation && approvalId) {
        const result = await action('/api/deliveries/seal', {candidate_id:candidateId, validation_id:validation.id,
          approval_id:approvalId, confirm:'SEAL'});
        setDeliveryId(result.id);
      }
    } catch (failure) { setError((failure as Error).message + '. Check saved review before trying another action.'); setReviewReady(false); }
    finally { setBusy(false); }
  }
  return <div className="mt-4 p-4 bg-white/5 rounded-lg space-y-3">
    <h3 className="font-semibold">Approve and archive this candidate</h3>
    <p className="text-xs text-white/60 break-all">Candidate: {candidateId}</p>
    <button disabled={busy || !reviewReady || !!deliveryId} onClick={() => void perform('validate')}>Validate candidate</button>
    <button disabled={busy} onClick={() => void recover()}>Check saved review</button>
    {busy && <p role="status">Checking or saving review action…</p>}
    {error && <p role="alert" className="text-amber-200">{error}</p>}
    {validation && <p>Candidate checks: {validation.status}</p>}
    {validation?.errors?.map((finding, index) => <p key={index} className="text-amber-200">{finding}</p>)}
    {reviewReady && validation?.status === 'PASS' && !approvalId && <fieldset disabled={busy} className="space-y-3">
      <label className="block">Approved by<input value={actor} onChange={event => setActor(event.target.value)} /></label>
      <label className="block">Authorization reference<input value={reference} onChange={event => setReference(event.target.value)} placeholder="Review decision or message reference" /></label>
      <label className="block"><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} /> I reviewed this candidate and approve its design.</label>
      <button disabled={!confirmed || !actor.trim() || !reference.trim()} onClick={() => void perform('approve')}>Record design approval</button>
    </fieldset>}
    {reviewReady && approvalId && !deliveryId && <><p>Design approval recorded. Sealing preserves this revision and its production recipe.</p>
      <button disabled={busy} onClick={() => void perform('seal')}>Seal release archive</button></>}
    {deliveryId && <p className="text-indigo-200 break-all">Archive sealed: {deliveryId}</p>}
    <p className="text-sm text-white/60">Design approval does not authorize upload. Review the archive before requesting separate upload approval.</p>
  </div>;
}
