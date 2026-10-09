import { useRef, useState } from 'react';
import { readHistory } from './historyRequest';
import { deliveryVerdict, type LocalDeliveryStatus } from './deliveryStatus';

type Delivery = { id: string; created_at: string; project_id: string; target: { platform: string; version: string } };
type Page = { deliveries: Delivery[]; next_cursor: string | null };
type Detail = LocalDeliveryStatus & { errors: string[]; remote_status: string };

export function DeliveryHistory() {
  const [deliveries, setDeliveries] = useState<Delivery[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [selected, setSelected] = useState('');
  const [detail, setDetail] = useState<Detail | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const generation = useRef(0);

  async function load(more = false) {
    const request = ++generation.current;
    setBusy(true); setError('');
    if (!more) { setSelected(''); setDetail(null); }
    try {
      const page = await readHistory<Page>('/api/deliveries?limit=20' +
        (more && cursor ? '&cursor=' + encodeURIComponent(cursor) : ''), 'delivery history');
      if (request !== generation.current) return;
      setDeliveries(previous => more ? [...previous, ...page.deliveries.filter(item => !previous.some(old => old.id === item.id))] : page.deliveries);
      setCursor(page.next_cursor); setLoaded(true);
    } catch (failure) { if (request === generation.current) setError(String(failure)); }
    finally { if (request === generation.current) setBusy(false); }
  }

  async function inspect(delivery: Delivery) {
    const request = ++generation.current;
    setSelected(delivery.id); setDetail(null); setBusy(true); setError('');
    try {
      const status = await readHistory<Detail>('/api/deliveries/' + encodeURIComponent(delivery.id), 'delivery verification');
      if (request === generation.current) setDetail(status);
    } catch (failure) { if (request === generation.current) setError(String(failure)); }
    finally { if (request === generation.current) setBusy(false); }
  }

  return <section className="m-6 p-5 border border-white/10 rounded-xl">
    <div className="flex flex-wrap justify-between gap-4"><h2 className="font-semibold">Delivery history</h2>
      <button disabled={busy} onClick={() => load()}>Load deliveries</button></div>
    <p className="text-sm text-white/60 my-3">Select a sealed release to check its archive and sources.</p>
    {busy && <p role="status">Checking deliveries…</p>}
    {error && <p role="alert" className="text-amber-200">{error}</p>}
    {loaded && !deliveries.length && !busy && <p>No sealed deliveries yet.</p>}
    <ul aria-label="Sealed deliveries" className="space-y-2 max-h-64 overflow-y-auto">{deliveries.map(delivery => <li key={delivery.id}>
      <button className={"w-full text-left " + (selected === delivery.id ? "bg-white/10" : "")} disabled={busy} aria-pressed={selected === delivery.id} onClick={() => inspect(delivery)}>
        {delivery.target.version} · {delivery.target.platform} · {new Date(delivery.created_at).toLocaleString()} · {delivery.id.slice(0, 8)}
      </button>
    </li>)}</ul>
    {cursor && <button disabled={busy} onClick={() => load(true)}>Load earlier deliveries</button>}
    {detail && <div className="mt-4 space-y-2" aria-live="polite">
      <h3 className="font-semibold">{deliveryVerdict(detail)}</h3>
      <p>Remote verification: {detail.remote_status === 'UNKNOWN' ? 'Unknown — check the publication record.' : detail.remote_status}</p>
      <ul>{detail.errors.map((finding, index) => <li className="text-amber-200" key={index}>{finding}</li>)}</ul>
      <button disabled={busy} onClick={() => {
        const delivery = deliveries.find(item => item.id === selected);
        if (delivery) void inspect(delivery);
      }}>Check archive again</button>
    </div>}
  </section>;
}
