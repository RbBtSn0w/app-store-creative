import { useEffect, useState } from 'react';

type Plan = { planDigest: string; decision: string; rows: { locale: string; target: string; after: string[] }[] };

function CampaignOrder({ campaign }: { campaign: string }) {
  const endpoint = '/api/cpp/' + encodeURIComponent(campaign);
  const [plan, setPlan] = useState<Plan>();
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [revision, setRevision] = useState(0);
  const [cell, setCell] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    fetch(endpoint + '/plan', { signal: controller.signal }).then(async response => {
      const value = await response.json();
      if (!response.ok) throw new Error(value.error);
      if (!controller.signal.aborted) { setPlan(value); setError(''); }
    }).catch(reason => { if (!controller.signal.aborted) setError(String(reason)); });
    return () => controller.abort();
  }, [endpoint, revision]);
  async function move(row: Plan['rows'][number], index: number) {
    if (!plan) return;
    const order = [...row.after];
    [order[index - 1], order[index]] = [order[index], order[index - 1]];
    setSaving(true);
    try {
      const response = await fetch(endpoint + '/order', {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'If-Match': '"' + plan.planDigest + '"' },
        body: JSON.stringify({ locale: row.locale, target: row.target, order })
      });
      const value = await response.json();
      if (!response.ok) throw new Error(value.error);
      setPlan(value); setError('');
    } catch (reason) { setError(String(reason)); }
    finally { setSaving(false); }
  }
  return <div>{error && <p role="alert">{error} <button onClick={() => setRevision(v => v + 1)}>Reload</button></p>}
    {plan && plan.rows.length > 1 && <label>Language and device
      <select value={cell} onChange={event => setCell(event.target.value)}>
        <option value="">All</option>
        {plan.rows.map(row => <option key={row.locale + '/' + row.target} value={row.locale + '/' + row.target}>
          {row.locale} · {row.target}</option>)}
      </select></label>}
    {plan && ['createPage', 'updatePage'].includes(plan.decision) && plan.rows
      .filter(row => !cell || row.locale + '/' + row.target === cell).map(row =>
      <section key={row.locale + '/' + row.target}><h4>{row.locale} · {row.target}</h4>
        <ol>{row.after.map((id, index) => <li key={id}>{id}{index > 0 &&
          <button className="ml-2 underline" disabled={saving || Boolean(error)} onClick={() => move(row, index)}
            aria-label={'Move ' + id + ' earlier'}>Move earlier</button>}</li>)}</ol></section>)}</div>;
}

export function CustomProductPages() {
  const [selected, setSelected] = useState('');
  const [campaigns, setCampaigns] = useState<string[]>([]);
  const [error, setError] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    fetch('/api/cpp', { signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error('Could not load custom product pages');
        const data = await response.json();
        if (!controller.signal.aborted) setCampaigns(data.campaigns);
      })
      .catch(reason => { if (!controller.signal.aborted) setError(String(reason)); });
    return () => controller.abort();
  }, []);
  if (!campaigns.length && !error) return null;
  return <section aria-label="Custom product pages">
    <h3 className="font-semibold">Custom product pages</h3>
    {error && <p role="alert">{error}</p>}
    <ul>{campaigns.map(key => <li key={key}><a className="underline" target="_blank" rel="noreferrer"
      href={'/api/cpp/' + encodeURIComponent(key) + '/review'}>{key} · Compare pages</a> <button className="ml-2 underline" onClick={() => setSelected(key)}>Review order</button></li>)}</ul>
    {selected && <CampaignOrder key={selected} campaign={selected} />}
  </section>;
}
