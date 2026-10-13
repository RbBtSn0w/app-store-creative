import { useEffect, useRef, useState } from 'react';
import { readHistory } from './historyRequest';
import { formatInventoryBytes, inventoryStatus, parseInventory, type Inventory, type InventoryCopy } from './inventoryPresentation';

const copyFindings: [keyof InventoryCopy, string][] = [
  ['extra_files', 'Additional files'], ['missing_files', 'Missing files'], ['changed_files', 'Changed files'],
  ['identity_conflicts', 'Replaced files'], ['unregistered_payloads', 'Files with unverified ownership'], ['unsafe_links', 'Unsafe links'],
];
function Copies({ title, items }: { title: string; items: InventoryCopy[] }) {
  return <div className="space-y-2"><h3 className="font-semibold">{title} · {items.length}</h3>
    {!items.length && <p className="text-sm text-white/60">None reported.</p>}
    <ul className="space-y-2 max-h-80 overflow-y-auto">{items.map((item, index) => <li key={`${item.id || item.relocation_id}/${item.path}/${index}`} className="p-3 bg-white/5 rounded-lg">
      <p>{item.phase && item.phase !== item.status && <>{inventoryStatus(item.phase)} · </>}{inventoryStatus(item.status)} · {formatInventoryBytes(item.observed_logical_bytes)}</p>
      <p className="text-xs text-white/60 break-all">{item.path}</p>
      <details className="text-sm mt-2"><summary>File details</summary>
        <p className="text-white/60 break-all">Operation: {item.id || item.relocation_id}</p>
        {copyFindings.map(([field, label]) => { const files = item[field]; return Array.isArray(files) && files.length > 0 ?
          <div key={field} className="mt-2 text-amber-200"><p>{label} · {files.length}</p><ul>{files.map((file, index) => <li className="break-all" key={index}>{file}</li>)}</ul></div> : null; })}
        {!!item.purged_files?.length && <p>{item.purged_files.length} files have deletion evidence.</p>}
      </details>
    </li>)}</ul>
  </div>;
}
export function InventoryReport({ inventory }: { inventory: Inventory }) {
  const measures = [['active_object_bytes', 'Local media'], ['quarantine_file_bytes', 'Isolated media'],
    ['other_object_file_bytes', 'Other object files'], ['work_file_bytes', 'Working files'],
    ['release_directory_bytes', 'Release archives'], ['publication_directory_bytes', 'Publication records']] as const;
  const issues = [['corrupt', 'Damaged media'], ['missing', 'Missing media'], ['unobserved_registered', 'Media not observed'], ['orphan_files', 'Unregistered media'],
    ['unknown_files', 'Unknown object files'], ['unknown_quarantine_files', 'Unknown isolated files'],
    ['corrupt_quarantine_files', 'Damaged isolated files'], ['unsafe_links', 'Unsafe object links']] as const;
  const findings = [...inventory.relocation_backups.unverified_operations, ...inventory.quarantine_preparations.unverified_operations,
    ...(inventory.relocation_backups.disposition_errors || [])];
  return <div className="space-y-5 mt-4">
    <p>{inventory.objects.reference_count} registered assets · {inventory.objects.registered_identities} distinct media objects · {inventory.objects.active_count === null ? 'Local object count not observed' : `${inventory.objects.active_count} observed local objects`}</p>
    <dl className="grid grid-cols-2 lg:grid-cols-3 gap-3">{measures.map(([field, label]) => <div className="p-3 bg-white/5 rounded-lg" key={field}>
      <dt className="text-sm text-white/60">{label}</dt><dd className="font-semibold">{formatInventoryBytes(inventory.capacity[field] as number | null)}</dd>
    </div>)}</dl>
    <p className="text-sm text-white/60">Sizes describe observed local files. Copies can share disk blocks; these figures are not a promise of recoverable space. Git history, LFS remote storage and external storage are not measured here.</p>
    <p className="text-sm">{inventory.observation_errors.some(error => error.area === 'objects') ?
      'Isolation and deletion presence not observed' :
      `${inventory.objects.quarantined.length} media objects isolated · ${inventory.objects.purged.length} media objects deleted`}</p>
    {!!inventory.observation_errors.length && <div role="alert" className="text-amber-200"><h3 className="font-semibold">Storage could not be fully checked</h3>
      <ul>{inventory.observation_errors.map((error, index) => <li className="text-sm break-all mt-2" key={index}>
        {({objects:'Media library', work:'Working files', releases:'Release archives', publications:'Publication records'} as Record<string, string>)[error.area] || error.area}: {error.reason}
        <p className="text-white/60">{error.path}</p>
      </li>)}</ul></div>}
    <div><h3 className="font-semibold">Media exceptions</h3>
      {issues.map(([field, label]) => inventory.objects[field].length > 0 && <details key={field} className="mt-2 text-amber-200">
        <summary>{label} · {inventory.objects[field].length}</summary><ul className="max-h-48 overflow-y-auto">{inventory.objects[field].map((path, index) => <li className="text-sm break-all" key={index}>{path}</li>)}</ul>
      </details>)}
      {!inventory.observation_errors.some(error => error.area === 'objects') && !issues.some(([field]) => inventory.objects[field].length > 0) && <p className="text-sm text-white/60">No media exceptions reported in the observed local scope.</p>}
      {!!inventory.other_unsafe_links.length && <details className="mt-2 text-amber-200"><summary>Unsafe links in working files or archives · {inventory.other_unsafe_links.length}</summary>
        <ul>{inventory.other_unsafe_links.map((path, index) => <li className="text-sm break-all" key={index}>{path}</li>)}</ul></details>}
    </div>
    {!!findings.length && <div role="alert" className="text-amber-200"><h3 className="font-semibold">Operations needing verification · {findings.length}</h3>
      <ul>{findings.map((finding, index) => <li className="text-sm break-all mt-2" key={index}>{finding.id || finding.relocation_id || 'Operation'}: {finding.reason}</li>)}</ul></div>}
    <Copies title="Retained migration copies" items={inventory.relocation_backups.copies} />
    <Copies title="Migration staging" items={inventory.relocation_backups.staging} />
    <Copies title="Isolation preparations" items={inventory.quarantine_preparations.operations} />
  </div>;
}
export function InventoryView() {
  const [inventory, setInventory] = useState<Inventory | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [checked, setChecked] = useState('');
  const generation = useRef(0);
  useEffect(() => () => { generation.current++; }, []);
  async function load() {
    const request = ++generation.current;
    setBusy(true); setError(''); setInventory(null); setChecked('');
    try {
      const result = parseInventory(await readHistory<unknown>('/api/inventory', 'asset inventory'));
      if (request !== generation.current) return;
      setInventory(result); setChecked(new Date().toLocaleString());
    } catch (failure) { if (request === generation.current) setError(failure instanceof Error ? failure.message : String(failure)); }
    finally { if (request === generation.current) setBusy(false); }
  }
  return <section className="m-6 p-5 border border-white/10 rounded-xl" aria-label="Asset inventory">
    <div className="flex flex-wrap justify-between gap-4"><h2 className="font-semibold">Asset inventory</h2>
      <button disabled={busy} onClick={() => load()}>Check storage</button></div>
    <p className="text-sm text-white/60 my-3">Review retained media, working files and migration copies. Storage checks report the saved project; unsaved edits are not included.</p>
    {busy && <p role="status">Checking stored files…</p>}
    {error && <p role="alert" className="text-amber-200">{error}</p>}
    {inventory && <><p className="text-xs text-white/60">Checked at {checked}. Check again after producing or maintaining files.</p><InventoryReport inventory={inventory} /></>}
  </section>;
}
