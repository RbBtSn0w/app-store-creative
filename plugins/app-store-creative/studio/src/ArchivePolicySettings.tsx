import type { ArchivePolicy } from './types';

export function ArchivePolicySettings({ policy, onChange, disabled = false }: {
  policy?: ArchivePolicy;
  onChange: (policy: ArchivePolicy | undefined) => void;
  disabled?: boolean;
}) {
  return <section className="m-6 p-5 border border-white/10 rounded-xl" aria-label="Archive policy">
    <h2 className="font-semibold">Release archive</h2>
    <p className="text-sm text-white/60 my-3">Choose before producing a release run. Save your choice, then produce a new run; existing candidates retain their original choice.</p>
    <label>Media storage<select disabled={disabled} value={policy?.mediaMode || ''} onChange={event => {
      const mode = event.target.value;
      if (mode === '') onChange(undefined);
      else if (mode === 'external') onChange({ schema_version: 1, mediaMode: 'external', backend: '' });
      else if (mode === 'git' || mode === 'lfs') onChange({ schema_version: 1, mediaMode: mode });
    }}>
      <option value="">Not selected — exploration only</option>
      <option value="git">Git files</option>
      <option value="lfs">Git LFS</option>
      <option value="external">External media storage</option>
    </select></label>
    {policy?.mediaMode === 'external' && <>
      <label>Backend name<input disabled={disabled} required pattern="[A-Za-z0-9][A-Za-z0-9_.-]{0,63}" value={policy.backend}
        onChange={event => onChange({ ...policy, backend: event.target.value })} /></label>
      <p className="text-sm text-white/60">Use the shared name of an existing backend. Its access location is configured privately on this computer.</p>
    </>}
  </section>;
}
