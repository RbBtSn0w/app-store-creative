import type { CreativeConfig } from './types';
import { changeStorageRoot, storageRoots, storageSaveConflict, type StoragePreview } from './storagePreview';

export function StorageSettings({ config, onChange, onCheck, report, error, checking=false, disabled=false }:
  {config:CreativeConfig; onChange:(config:CreativeConfig) => void; onCheck:() => void;
    report?:StoragePreview|null; error?:string; checking?:boolean; disabled?:boolean}) {
  const conflict = report ? storageSaveConflict(report) : null;
  return <section aria-label="Output directories" className="m-6 p-5 rounded-xl border border-white/10 space-y-3">
    <h2 className="font-semibold">Output directories</h2>
    <p className="text-sm text-white/60">Relative paths start from this project. Leave a field empty to use its default. Previewing does not save or move files.</p>
    <fieldset disabled={disabled || checking} className="grid sm:grid-cols-2 gap-4">
      {storageRoots.map(([key, label, placeholder]) => <label key={key}>{label}
        <input value={config.storage?.[key] || ''} placeholder={placeholder}
          onChange={event => onChange(changeStorageRoot(config, key, event.target.value))} />
      </label>)}
    </fieldset>
    <button type="button" disabled={disabled || checking} onClick={onCheck}>{checking ? 'Checking directories…' : 'Preview directories'}</button>
    {error && <p role="alert" className="text-red-300">{error}</p>}
    {report && <div className="space-y-2"><p className="text-sm text-white/60">Resolved for this draft. Saving checks the paths again.</p>
      <dl className="space-y-2">{storageRoots.map(([key, label]) => <div key={key}><dt>{label}
        <span className="text-sm text-white/60"> · {report.roots[key].source === 'local' ? 'Host-local override' : report.roots[key].source === 'project' ? 'Project setting' : report.roots[key].source === 'derived' ? 'Derived from working directory' : 'Default'}</span></dt>
        <dd className="text-sm break-all text-white/70">{report.roots[key].resolved}</dd></div>)}</dl>
      {conflict && <p role="alert" className="text-amber-300">{conflict}</p>}
    </div>}
  </section>;
}
