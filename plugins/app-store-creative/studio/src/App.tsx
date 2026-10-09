import React, { useCallback, useEffect, useRef, useState } from 'react';
import { CardView } from './components/CardView';
import { CreativeConfig, TargetDevice, TARGET_DIMENSIONS, CardConfig } from './types';
import { defaultCardLayout, localizedFields, resolveCard, updateVariant } from './project';
import { releaseState } from './releaseState';
import { ExportView } from './ExportView';
import { STYLE_PRESETS } from './stylePresets';
import { downloadDraft } from './downloadDraft';
import { RunHistory } from './RunHistory';
import { DeliveryHistory } from './DeliveryHistory';
import { InventoryView } from './InventoryView';
import { MediaBudgetPanel } from './MediaBudgetPanel';
import { OperationHistory } from './OperationHistory';
import { PublicationHistory } from './PublicationHistory';
import { ObservationEvidence } from './ObservationEvidence';
import { MaintenancePanel } from './MaintenancePanel';
import { RelocationMaintenance } from './RelocationMaintenance';
import { RelocationStatusPanel } from './RelocationStatusPanel';
import { RelocationActions } from './RelocationActions';
import { RelocationRecovery } from './RelocationRecovery';
import { CandidateApproval } from './CandidateApproval';
import { StorageSettings } from './StorageSettings';
import { ArchivePolicySettings } from './ArchivePolicySettings';
import { loadStoragePreview, storageSaveConflict, type StoragePreview } from './storagePreview';

const initialProject = (): CreativeConfig => ({
  project: { id: 'my-app', name: '', bundleId: '', defaultLocale: 'en-US', locales: ['en-US', 'zh-Hans'] },
  targets: ['iphone_6_9', 'mac_16_10'], connectedTrack: true,
  theme: { stylePreset: 'liquid_glass', background: { type: 'gradient', colors: ['#0A0E1A', '#311042'] } },
  cards: [], studio: { requireExportEvidence: true },
});
const layouts: NonNullable<CardConfig['layout']>[] = ['phone_bottom', 'phone_center', 'phone_tilt_left', 'phone_tilt_right',
  'phone_bleed', 'phone_floating_isometric', 'phone_perspective_hero', 'mac_native_hero', 'mac_native_left', 'mac_native_right', 'pure_text'];
const layoutName = (name: string) => name.replaceAll('_', ' ');
const fileData = (file: File) => new Promise<string>((resolve, reject) => {
  const reader = new FileReader(); reader.onerror = () => reject(new Error('Could not read capture'));
  reader.onload = () => resolve(String(reader.result).split(',')[1]); reader.readAsDataURL(file);
});

async function request(path: string, data?: unknown, revision?: string, timeout = 20000) {
  const response = await fetch(path, { method: data === undefined ? 'GET' : 'POST',
    headers: { 'Content-Type': 'application/json', ...(revision ? { 'If-Match': revision } : {}) },
    ...(data === undefined ? {} : { body: JSON.stringify(data) }), signal: AbortSignal.timeout(timeout) });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || `Request failed (${response.status})`);
  return { body, revision: response.headers.get('ETag') || undefined };
}

export const App: React.FC = () => {
  const [config, setConfig] = useState<CreativeConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [target, setTarget] = useState<TargetDevice>('iphone_6_9');
  const [locale, setLocale] = useState('en-US');
  const [selected, setSelected] = useState('');
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [storagePreview, setStoragePreview] = useState<StoragePreview | null>(null);
  const [storageError, setStorageError] = useState('');
  const [checkingStorage, setCheckingStorage] = useState(false);
  const storageCheckGeneration = useRef(0);
  const [busy, setBusy] = useState(false);
  const [operation, setOperation] = useState<'import' | 'export'>('import');
  const [layoutFindings, setLayoutFindings] = useState<Record<string, string>>({});
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [status, setStatus] = useState<{ running?: boolean; completed?: number; total?: number; configRevision?: string; inputErrors?: string[]; candidate_id?: string | null; run_id?: string;
    validation?: { status: string; errors: string[]; assets_count: number; assets: Record<string, unknown> } | null }>({});
  const state = useRef(config); state.current = config;
  const revision = useRef<string | undefined>(undefined);
  const version = useRef(0);
  const draftDirty = useRef(dirty); draftDirty.current = dirty;
  const saveJob = useRef<Promise<string | undefined> | null>(null);
  const storageChanged = useRef(false);
  const params = new URLSearchParams(window.location.search);
  const exporting = params.get('export') === 'true';
  const refreshStatus = useCallback(async () => {
    const reviewedRevision = revision.current;
    try { const { body } = await request('/api/status');
      if (reviewedRevision !== revision.current) return;
      setStatus(body);
      if (body.configRevision && body.configRevision !== reviewedRevision) setError(current => current || 'Project changed outside this tab. Keep your draft or reload before saving.');
      else if (body.error) setError(current => current || body.error);
    } catch (reason) { setStatus({}); setError(current => current || `Could not check current files: ${(reason as Error).message}. Try again.`); }
  }, []);

  useEffect(() => {
    request('/api/config').then(({ body, revision: next }) => {
      revision.current = next;
      if (body.cards && body.project) {
        setConfig(body); setTarget(body.targets?.[0] || 'iphone_6_9');
        setLocale(body.project.defaultLocale || 'en-US'); setSelected(body.cards[0]?.id || '');
        if (!exporting) void refreshStatus();
      } else if (!exporting) { setConfig(initialProject()); setCreating(true); }
      else setError('No project is configured');
    }).catch(reason => setError(reason.message)).finally(() => setLoading(false));
  }, []);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (draftDirty.current) { event.preventDefault(); event.returnValue = ''; } };
    window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn);
  }, []);
  useEffect(() => {
    if (!busy) return;
    const timer = setInterval(refreshStatus, 1000); return () => clearInterval(timer);
  }, [busy, refreshStatus]);
  useEffect(() => {
    if (exporting) return;
    const onFocus = () => { if (!draftDirty.current) void refreshStatus(); };
    window.addEventListener('focus', onFocus); return () => window.removeEventListener('focus', onFocus);
  }, [refreshStatus]);

  const edit = (change: CreativeConfig | ((current: CreativeConfig) => CreativeConfig)) => {
    if (!state.current) return;
    const next = typeof change === 'function' ? change(state.current) : change;
    state.current = next; setConfig(next); version.current++; setDirty(true); setStatus({}); setNotice('');
    storageCheckGeneration.current++; setStoragePreview(null); setStorageError(''); setCheckingStorage(false);
  };
  const previewDirectories = async (snapshot = state.current): Promise<StoragePreview> => {
    if (!snapshot) throw new Error('Create a project first');
    const generation = ++storageCheckGeneration.current, startedAt = version.current;
    setStoragePreview(null); setStorageError(''); setCheckingStorage(true);
    try {
      const report = await loadStoragePreview(snapshot);
      if (generation === storageCheckGeneration.current && startedAt === version.current) setStoragePreview(report);
      return report;
    } catch (reason) {
      if (generation === storageCheckGeneration.current && startedAt === version.current) setStorageError((reason as Error).message);
      throw reason;
    } finally { if (generation === storageCheckGeneration.current) setCheckingStorage(false); }
  };
  const save = (): Promise<string | undefined> => {
    if (storageChanged.current) return Promise.reject(new Error('Storage switching was requested. Reload the project after checking relocation status.'));
    if (saveJob.current) return saveJob.current;
    if (!state.current) return Promise.reject(new Error('Create a project first'));
    const snapshot = state.current, startedAt = version.current;
    setSaving(true); setError('');
    const job = previewDirectories(snapshot).then(report => {
      const conflict = storageSaveConflict(report);
      if (conflict) throw new Error(conflict);
      return request('/api/config', snapshot, revision.current);
    }).then(({ revision: next }) => {
      revision.current = next;
      if (version.current === startedAt) setDirty(false);
      setStatus({}); void refreshStatus(); setNotice(version.current === startedAt ? 'Project saved' : 'Earlier edits saved. Newer changes still need saving.'); return next;
    }).finally(() => { saveJob.current = null; setSaving(false); });
    saveJob.current = job; return job;
  };
  const exportProject = async (scope: 'all' | 'selected') => {
    setOperation('export'); setBusy(true); setError(''); setNotice('');
    try {
      const startedAt = version.current;
      await save();
      if (version.current !== startedAt) throw new Error('Changes arrived while saving. Review and export again.');
      const health = await request('/api/health');
      if (!health.body.chrome) throw new Error('Install Chrome or Chromium before exporting. Your project is saved.');
      const { body } = await request('/api/export', { scope, target, locale }, revision.current, 30 * 60 * 1000);
      setStatus({ validation: body.validation, candidate_id: body.result?.candidate_id, run_id: body.result?.run_id });
      if (!body.ok) throw new Error(body.result?.errors?.join('\n') || 'Export needs attention');
      setNotice(scope === 'selected' ? 'Selected set exported. Full release verification is shown separately.' : 'Full matrix exported. Review the verification result.');
    } catch (reason) { setError((reason as Error).message); }
    finally { setBusy(false); await refreshStatus(); }
  };
  const importFiles = async (files: FileList | File[], replace = false) => {
    if (!state.current) return;
    setOperation('import'); setBusy(true); setError('');
    const assignmentTarget = target, assignmentLocale = locale, assignmentId = selected;
    try {
      for (const [index, file] of Array.from(files).entries()) {
        const { body } = await request('/api/assets', { name: file.name, data: await fileData(file) });
        let id = assignmentId;
        if (!replace || index > 0 || !id) {
          id = `card-${crypto.randomUUID().slice(0, 8)}`;
          const newCard: CardConfig = { id, headline: file.name.replace(/\.[^.]+$/, ''),
            layout: assignmentTarget.startsWith('mac_') ? 'mac_native_hero' : 'phone_bottom' };
          edit(current => ({ ...current, cards: [...current.cards, newCard] })); setSelected(id);
        }
        edit(current => updateVariant(current, id, assignmentTarget, assignmentLocale, { screenshot: body.path }));
      }
      setNotice('Captures imported. Review assignments and copy before exporting.');
    } catch (reason) { setError((reason as Error).message); }
    finally { setBusy(false); }
  };
  const recoverDraft = () => {
    downloadDraft(state.current);
  };

  if (loading) return <main className="p-10">Opening your project…</main>;
  if (!config) return <main className="p-10" role="alert">{error || 'Could not open the project'} <button onClick={() => location.reload()}>Retry</button></main>;
  if (exporting) return <ExportView config={config} id={params.get('card') || ''}
    target={(params.get('target') || 'iphone_6_9') as TargetDevice} locale={params.get('locale') || 'en-US'} />;
  const active = config.cards.find(card => card.id === selected);
  const resolved = active ? resolveCard(config, active, target, locale) : undefined;
  const fields = active ? localizedFields(config, active, target, locale) : {};
  const defaultLocale = config.project.defaultLocale || 'en-US';
  const inherited = locale !== defaultLocale && (!Object.hasOwn(fields, 'headline') || (resolved?.layout !== 'pure_text' && !Object.hasOwn(fields, 'screenshot')));
  const errors = status.validation?.errors || [];
  const layoutErrors = config.cards.some(card => !!layoutFindings[`${target}/${locale}/${card.id}`]);
  const checked = !layoutErrors && !dirty && !busy && !error && status.configRevision === revision.current && status.validation?.status === 'PASS';
  const verified = checked && config.studio?.requireExportEvidence === true;
  const policyChecked = checked && !config.studio?.requireExportEvidence;
  const total = config.cards.length * config.targets.length * (config.project.locales?.length || 1);
  const stateLabel = releaseState({ hasCards: !!config.cards.length, dirty, saving, busy,
    exporting: operation === 'export', verified, policyChecked, error: !!error, inputsChecked: status.inputErrors !== undefined,
    inputsMissing: !!status.inputErrors?.length, layoutErrors }) +
    (busy && status.total ? ` · ${status.completed || 0}/${status.total}` : '');
  const mutate = (change: Parameters<typeof updateVariant>[4]) => { if (active) edit(current => updateVariant(current, active.id, target, locale, change)); };

  return <main className="min-h-screen">
    <header className="border-b border-white/10 px-6 py-5 flex flex-wrap gap-4 justify-between items-center">
      <div><p className="text-xs uppercase tracking-widest text-indigo-300">App Store Creative</p>
        <h1 className="text-xl font-semibold">{config.project.name || 'Your first screenshot set'}</h1>
        <p role="status" className={verified ? 'text-emerald-300 text-sm' : 'text-white/60 text-sm'}>{stateLabel}</p></div>
      {!creating && <div className="flex flex-wrap gap-2">
        <button disabled={busy || saving} onClick={() => save().catch(reason => setError(reason.message))}>{saving ? 'Saving…' : 'Save project'}</button>
        <button disabled={busy || !config.cards.length} onClick={() => exportProject('selected')}>Export selected set</button>
        <button className="primary" disabled={busy || !config.cards.length} onClick={() => exportProject('all')}>Export full matrix</button>
      </div>}
    </header>
    {error && <section role="alert" className="mx-6 mt-4 p-4 bg-red-950/40 border border-red-400/30 rounded-xl whitespace-pre-wrap">
      {error}<div className="flex gap-3 mt-2"><button onClick={recoverDraft}>Download current draft</button>
        <button onClick={() => { if (!dirty || confirm('Reload the project? Download your draft first to preserve unsaved changes.')) location.reload(); }}>Reload project</button></div></section>}
    {notice && <p role="status" className="mx-6 mt-4 text-indigo-200">{notice}</p>}
    <ArchivePolicySettings policy={config.archivePolicy} disabled={busy || saving} onChange={policy => edit(current => ({ ...current, archivePolicy: policy }))} />
    <StorageSettings config={config} onChange={edit} report={storagePreview} error={storageError}
      checking={checkingStorage} disabled={busy || saving}
      onCheck={() => { void previewDirectories().catch(() => {}); }} />
    {creating ? <form className="max-w-xl mx-auto p-8 space-y-5" onSubmit={async event => {
      event.preventDefault(); try { await save(); setTarget(state.current!.targets[0]); setLocale(state.current!.project.defaultLocale || 'en-US'); setCreating(false); } catch (reason) { setError((reason as Error).message); }
    }}><h2 className="text-2xl font-semibold">Start with your real app</h2>
      <p className="text-white/60">Choose where your screenshots will appear, then bring your real captures. Everything stays in this project.</p>
      <label>Project ID<input required pattern="[A-Za-z0-9][A-Za-z0-9_-]*" value={config.project.id} onChange={event => edit(current => ({ ...current, project: { ...current.project, id: event.target.value } }))} /></label>
      <label>App name<input required value={config.project.name} onChange={event => edit(current => ({ ...current, project: { ...current.project, name: event.target.value } }))} /></label>
      <label>Bundle ID<input required value={config.project.bundleId} onChange={event => edit(current => ({ ...current, project: { ...current.project, bundleId: event.target.value } }))} /></label>
      <label>Languages (comma separated)<input required defaultValue={(config.project.locales || [defaultLocale]).join(', ')} onChange={event => { const locales = [...new Set(event.target.value.split(',').map(value => value.trim()).filter(Boolean))]; edit(current => ({ ...current, project: { ...current.project, locales, defaultLocale: locales[0] || 'en-US' } })); }} /></label>
      <fieldset><legend>Targets</legend><div className="grid grid-cols-2 gap-2 mt-2">{Object.entries(TARGET_DIMENSIONS).map(([id, dimensions]) => <label className="flex gap-2 items-center" key={id}>
        <input type="checkbox" checked={config.targets.includes(id as TargetDevice)} onChange={event => edit(current => ({ ...current, targets: event.target.checked ? [...current.targets, id as TargetDevice] : current.targets.filter(value => value !== id) }))} />{dimensions.displayName}</label>)}</div></fieldset>
      <button disabled={saving || !config.targets.length} className="primary" type="submit">Create project</button>
    </form> : <>
      <fieldset disabled={busy} className="flex flex-wrap gap-4 px-6 py-4 border-b border-white/10">
        <label>Target<select value={target} onChange={event => setTarget(event.target.value as TargetDevice)}>{config.targets.map(id => <option key={id} value={id}>{TARGET_DIMENSIONS[id]?.displayName || id}</option>)}</select></label>
        <label>Language<select value={locale} onChange={event => setLocale(event.target.value)}>{(config.project.locales || ['en-US']).map(value => <option key={value}>{value}</option>)}</select></label>
        <label>Visual style<select value={config.theme.stylePreset || ''} onChange={event => edit(current => ({ ...current, theme: { ...current.theme, stylePreset: event.target.value } }))}>
          <option value="">Project theme</option>{Object.entries(STYLE_PRESETS).map(([id, preset]) => <option key={id} value={id}>{preset.name}</option>)}</select></label>
        <label className="flex items-center gap-2"><input type="checkbox" checked={!!config.connectedTrack} onChange={event => edit(current => ({ ...current, connectedTrack: event.target.checked }))} />Connected background</label>
      </fieldset>
      <div className="grid lg:grid-cols-[260px_minmax(0,1fr)_320px] gap-0">
        <aside className="p-5 space-y-3 border-r border-white/10">
          <h2 className="font-semibold">Screenshots · {config.cards.length}</h2>
          <label className="upload">Add real captures<input type="file" accept="image/png,image/jpeg" multiple disabled={busy} onChange={event => { if (event.target.files) void importFiles(event.target.files); event.target.value = ''; }} /></label>
          <button disabled={busy} onClick={() => { const id = `card-${crypto.randomUUID().slice(0, 8)}`; edit(current => ({ ...current, cards: [...current.cards, { id, headline: 'Your headline', layout: 'pure_text' }] })); setSelected(id); }}>Add text card</button>
          <ol className="space-y-2">{config.cards.map((card, index) => <li key={card.id}>
            <button className={`w-full text-left ${selected === card.id ? 'border-indigo-400 bg-indigo-500/15' : ''}`} onClick={() => setSelected(card.id)}>{index + 1}. {resolveCard(config, card, target, locale).headline || 'Untitled'}</button>
          </li>)}</ol>
          <p className="text-xs text-white/50">{total} outputs declared. Each language and target needs reviewed copy and real source captures.</p>
        </aside>
        <section className="overflow-auto p-8 min-h-[500px]" aria-label="Screenshot previews"
          onDragOver={event => event.preventDefault()} onDrop={event => { event.preventDefault(); if (!busy) void importFiles(event.dataTransfer.files); }}>
          {!config.cards.length ? <div className="p-12 text-center border border-dashed border-white/20 rounded-2xl">
            <h2 className="text-xl mb-3">Bring your real app screens</h2><p className="text-white/60">Drop PNG or JPEG captures here. Select the intended target and language before importing.</p>
          </div> : <div className="flex gap-6 items-start">{config.cards.map((card, index) => <div key={card.id} className="shrink-0 cursor-pointer" onClick={() => setSelected(card.id)}>
            <CardView card={resolveCard(config, card, target, locale)} index={index} totalCards={config.cards.length}
              target={target} theme={config.theme} locale={locale} connected={config.connectedTrack}
              onReview={findings => { const key = `${target}/${locale}/${card.id}`, value = findings.join('. ');
                setLayoutFindings(current => current[key] === value ? current : { ...current, [key]: value }); }} />
          </div>)}</div>}
        </section>
        <aside className="p-5 border-l border-white/10">{active && resolved ? <fieldset disabled={busy} className="space-y-4">
          <h2 className="font-semibold">Edit selected screenshot</h2><p className="text-sm text-white/50">{TARGET_DIMENSIONS[target]?.displayName} · {locale}</p>
          {inherited && <div className="p-3 bg-amber-950/40 border border-amber-300/20 rounded-xl text-sm">Copy or capture inherits the default language.
            <label className="flex gap-2 mt-2"><input type="checkbox" checked={!!fields.inheritDefault} onChange={event => mutate({ inheritDefault: event.target.checked })} />I reviewed the inherited content</label></div>}
          <label>Headline<textarea value={resolved.headline} onChange={event => mutate({ headline: event.target.value })} /></label>
          <label>Subheadline<textarea value={resolved.subheadline || ''} onChange={event => mutate({ subheadline: event.target.value })} /></label>
          <label>Composition<select value={resolved.layout || defaultCardLayout(target)} onChange={event => mutate({ layout: event.target.value as CardConfig['layout'] })}>{layouts.map(value => <option key={value} value={value}>{layoutName(value)}</option>)}</select></label>
          {resolved.screenshot ? <img className="max-h-32 mx-auto rounded object-contain" src={resolved.screenshot} alt="Assigned real capture" /> : <p className="text-amber-200 text-sm">{resolved.layout === 'pure_text' ? 'Text-only composition. No capture is needed.' : 'No capture assigned to this composition.'}</p>}
          <label className="upload">Replace capture for {locale}<input type="file" accept="image/png,image/jpeg" onChange={event => { if (event.target.files) void importFiles(event.target.files, true); event.target.value = ''; }} /></label>
          <div className="flex gap-2"><button disabled={config.cards[0]?.id === active.id} onClick={() => edit(current => { const cards = [...current.cards]; const index = cards.findIndex(card => card.id === active.id); [cards[index - 1], cards[index]] = [cards[index], cards[index - 1]]; return { ...current, cards }; })}>Move earlier</button>
            <button disabled={config.cards.at(-1)?.id === active.id} onClick={() => edit(current => { const cards = [...current.cards]; const index = cards.findIndex(card => card.id === active.id); [cards[index + 1], cards[index]] = [cards[index], cards[index + 1]]; return { ...current, cards }; })}>Move later</button></div>
          <button onClick={() => { if (confirm('Remove this screenshot from the set? Its imported capture remains available in the project.')) { edit(current => ({ ...current, cards: current.cards.filter(card => card.id !== active.id) })); setSelected(''); } }}>Remove screenshot</button>
        </fieldset> : <p className="text-white/50">Select a screenshot to adjust its copy and assignments.</p>}</aside>
      </div>
      <section className="m-6 p-5 border border-white/10 rounded-xl">
        <div className="flex justify-between gap-4"><h2 className="font-semibold">Release review</h2><button disabled={busy} onClick={refreshStatus}>Check current files</button></div>
        <p className="text-sm text-white/60 my-3">{verified ? 'All declared assets passed local checks. No upload has occurred.' : policyChecked ? 'Candidate checks passed under this project’s policy. Rendering evidence is not required by the current policy.' : 'Export and verify the full matrix before preparing a store handoff.'} Each export is saved as a separate production attempt in the configured workspace.</p>
        {!config.studio?.requireExportEvidence && <button onClick={() => {
          edit(current => ({ ...current, project: { ...current.project, id: current.project.id || 'my-app' }, studio: { ...current.studio, requireExportEvidence: true } }));
          if (!config.project.id || !config.project.name || !config.project.bundleId) setCreating(true);
        }}>Require rendering evidence</button>}
        {!dirty && errors.length > 0 && <ul className="text-sm text-amber-200 space-y-1 max-h-52 overflow-auto">{errors.map((finding, index) => <li key={index}>{finding}</li>)}</ul>}
        {!dirty && status.candidate_id && status.validation?.assets && Object.keys(status.validation.assets).length > 0 &&
          <ul className="grid gap-2 my-3 text-sm">{(config.project.locales || [defaultLocale]).flatMap(language => config.targets.flatMap(device => config.cards.map(card => {
            const name = `${language}/${device}/${card.id}.png`;
            return Object.hasOwn(status.validation!.assets, name) ? <li key={name}><a className="text-indigo-200 underline" target="_blank" rel="noreferrer"
              href={'/api/artifacts/' + encodeURIComponent(status.candidate_id || '') + '/' + name.split('/').map(encodeURIComponent).join('/')}>{language} · {TARGET_DIMENSIONS[device]?.displayName} · {card.id}</a></li> : null;
          })))}</ul>}
        {verified && <p className="text-sm text-indigo-200">Next: ask your ASC agent to prepare the handoff, review these assets, and request separate upload approval.</p>}
      </section>
      {!dirty && status.candidate_id && <CandidateApproval key={status.candidate_id} candidateId={status.candidate_id} />}
      <RunHistory />
      <DeliveryHistory />
      <PublicationHistory />
      <ObservationEvidence />
      <InventoryView />
      <MediaBudgetPanel />
      <MaintenancePanel />
      <RelocationMaintenance />
          <RelocationActions onStorageChange={() => { storageChanged.current = true; setError('Storage switching was requested. Check relocation status, then reload before saving or exporting.'); }} />
      <RelocationStatusPanel />
      <RelocationRecovery onStorageChange={() => { storageChanged.current = true; setError('Recovery was requested. Check operation status, then reload before saving or exporting.'); }} />
      <OperationHistory />
    </>}
  </main>;
};
