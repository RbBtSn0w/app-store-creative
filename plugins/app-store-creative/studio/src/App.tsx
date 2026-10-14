import React, { useCallback, useEffect, useRef, useState } from 'react';
import { CardView } from './components/CardView';
import { CreativeConfig, TargetDevice, TARGET_DIMENSIONS, CardConfig, CardOffset } from './types';
import { defaultCardLayout, localizedFields, resolveCard, updateVariant } from './project';
import { releaseState } from './releaseState';
import { ExportView } from './ExportView';
import { STYLE_PRESETS } from './stylePresets';
import { downloadDraft } from './downloadDraft';
import { COPY_FORMULAS } from './copyFormulas';
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
import { CandidatePreviewMedia } from './CandidatePreviewMedia';
import { StorageSettings } from './StorageSettings';
import { ArchivePolicySettings } from './ArchivePolicySettings';
import { loadStoragePreview, storageSaveConflict, assertCurrentSave, type StoragePreview } from './storagePreview';
import { classifyPose } from './layoutReview';

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
  const [workspaceMode, setWorkspaceMode] = useState<'canvas' | 'lifecycle'>('canvas');
  const [canvasNarrowTab, setCanvasNarrowTab] = useState<'cards' | 'canvas' | 'inspector'>('canvas');
  const [lifecycleTab, setLifecycleTab] = useState<'approval' | 'governance'>('approval');
  const [inspectorTab, setInspectorTab] = useState<'copy' | 'spatial' | 'ambiance' | 'review'>('copy');
  const [critiqueNotesByCard, setCritiqueNotesByCard] = useState<Record<string, string>>({});
  const critiqueNotesByCardRef = useRef<Record<string, string>>({}); critiqueNotesByCardRef.current = critiqueNotesByCard;
  const [dirtyCritiqueCards, setDirtyCritiqueCards] = useState<Record<string, boolean>>({});
  const dirtyCritiqueCardsRef = useRef<Record<string, boolean>>({}); dirtyCritiqueCardsRef.current = dirtyCritiqueCards;
  const [showCopyIdeas, setShowCopyIdeas] = useState(false);
  const [syncingCritique, setSyncingCritique] = useState(false);
  const [critiqueNotice, setCritiqueNotice] = useState('');

  const state = useRef(config); state.current = config;
  const revision = useRef<string | undefined>(undefined);
  const version = useRef(0);
  const draftDirty = useRef(dirty); draftDirty.current = dirty;
  const saveJob = useRef<Promise<string | undefined> | null>(null);
  const storageChanged = useRef(false);
  const params = new URLSearchParams(window.location.search);
  const exporting = params.get('export') === 'true';

  const arcRoles = ['Hero', 'Mechanism', 'Depth', 'Ecosystem', 'CTA'];
  const getCardRole = (idx: number) => arcRoles[idx] || 'Feature';

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

    request('/api/critique').then(({ body }) => {
      if (!body || typeof body !== 'object') return;
      const directives = (body as { directives?: Record<string, { notes?: string }> }).directives || {};
      const initialNotes: Record<string, string> = {};
      for (const [cardId, item] of Object.entries(directives)) {
        if (item && typeof item.notes === 'string') {
          initialNotes[cardId] = item.notes;
        }
      }
      setCritiqueNotesByCard(initialNotes);
    }).catch(() => {});
  }, []);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (draftDirty.current || Object.values(dirtyCritiqueCardsRef.current).some(Boolean)) { event.preventDefault(); event.returnValue = ''; } };
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
      assertCurrentSave({storageChanged: storageChanged.current, version: version.current}, startedAt);
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

  const updateOffset = (partial: Partial<CardOffset>) => {
    mutate({ deviceOffset: { ...(resolved?.deviceOffset || {}), ...partial } });
  };

  const applyPresetPose = (pose: 'hero' | 'gaze' | 'grounded' | 'flat') => {
    if (pose === 'hero') {
      updateOffset({ scale: 1.05, rotate: 0, rotateX: 4, rotateY: 0, x: 0, y: 15 });
    } else if (pose === 'gaze') {
      const isRight = resolved?.layout === 'mac_native_right';
      updateOffset({ scale: 1.02, rotate: isRight ? 2 : -2, rotateX: 4, rotateY: isRight ? -8 : 8, x: isRight ? 10 : -10, y: 0 });
    } else if (pose === 'grounded') {
      updateOffset({ scale: 0.95, rotate: 0, rotateX: 0, rotateY: 0, x: 0, y: 0 });
    } else if (pose === 'flat') {
      updateOffset({ scale: 1.0, rotate: 0, rotateX: 0, rotateY: 0, x: 0, y: 0 });
    }
  };

  const syncCritique = async () => {
    if (!active) return;
    setSyncingCritique(true); setCritiqueNotice('');
    try {
      const note = critiqueNotesByCard[active.id] || '';
      const payload = {
        card_id: active.id,
        role: getCardRole(config.cards.findIndex(c => c.id === active.id)),
        target,
        locale,
        headline: resolved?.headline || '',
        subheadline: resolved?.subheadline || '',
        layout: resolved?.layout,
        deviceOffset: resolved?.deviceOffset || {},
        theme: {
          stylePreset: config.theme.stylePreset,
          angle: config.theme.background?.angle ?? 135,
        },
        notes: note,
        timestamp: new Date().toISOString(),
      };
      await request('/api/critique', payload);
      setDirtyCritiqueCards(prev => {
        if (critiqueNotesByCardRef.current[active.id] !== note) {
          return prev;
        }
        return { ...prev, [active.id]: false };
      });
      setCritiqueNotice('✓ Directives saved to .creative/review-directives.json');
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setSyncingCritique(false);
    }
  };

  const copyCritiqueMarkdown = () => {
    if (!active) return;
    const role = getCardRole(config.cards.findIndex(c => c.id === active.id));
    const note = critiqueNotesByCard[active.id] || '';
    const md = `### [Creative Review Directive] Card: ${active.id} (Arc Role: ${role})
- Target: ${target} | Locale: ${locale}
- 3D Transforms:
  - Pitch (rotateX): ${resolved?.deviceOffset?.rotateX ?? 0}°
  - Yaw (rotateY): ${resolved?.deviceOffset?.rotateY ?? 0}°
  - Roll (rotate): ${resolved?.deviceOffset?.rotate ?? 0}°
  - Scale: ${resolved?.deviceOffset?.scale ?? 1.0}
  - Offset: (${resolved?.deviceOffset?.x ?? 0}px, ${resolved?.deviceOffset?.y ?? 0}px)
- Copy:
  - Headline: "${resolved?.headline || ''}"
  - Subheadline: "${resolved?.subheadline || ''}"
- Layout: ${resolved?.layout || 'default'}
- Theme: Preset=${config.theme.stylePreset || 'default'}, Angle=${config.theme.background?.angle ?? 135}°
- Critique Notes: "${note || 'No custom notes'}"
- Workflow Action: Ingest parameters into creative.config.json, rerun offline headless verification, and regenerate preview artifact.`;
    void navigator.clipboard.writeText(md).then(() => {
      setCritiqueNotice('✓ Markdown directive copied to clipboard');
    }).catch(reason => {
      setError(`Could not copy directive: ${(reason as Error).message}`);
    });
  };

  return <main className="min-h-screen">
    <header className="border-b border-white/10 px-6 py-4 flex flex-wrap gap-4 justify-between items-center bg-[#0F121C]/80 backdrop-blur-md sticky top-0 z-50">
      <div>
        <div className="flex items-center gap-2">
          <p className="text-xs uppercase tracking-widest text-indigo-300 font-mono">App Store Creative Studio</p>
          <span className="text-[10px] uppercase font-mono px-1.5 py-0.2 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">v3.0</span>
        </div>
        <h1 className="text-xl font-semibold mt-0.5">{config.project.name || 'Your first screenshot set'}</h1>
        <p role="status" className={verified ? 'text-emerald-300 text-xs' : 'text-white/60 text-xs'}>{stateLabel}</p>
      </div>

      {!creating && (
        <div className="flex items-center gap-3">
          {/* Dual-Mode Workspace Switcher */}
          <div className="flex bg-white/5 p-1 rounded-xl border border-white/10 text-xs">
            <button type="button" className={`px-3 py-1.5 rounded-lg font-medium transition ${workspaceMode === 'canvas' ? 'bg-indigo-600 text-white shadow' : 'text-white/60 hover:text-white'}`}
              onClick={() => setWorkspaceMode('canvas')}>
              🎨 Canvas & Review
            </button>
            <button type="button" className={`px-3 py-1.5 rounded-lg font-medium transition ${workspaceMode === 'lifecycle' ? 'bg-indigo-600 text-white shadow' : 'text-white/60 hover:text-white'}`}
              onClick={() => setWorkspaceMode('lifecycle')}>
              📋 Lifecycle & Audit
            </button>
          </div>

          <div className="flex gap-2">
            <button disabled={busy || saving} onClick={() => save().catch(reason => setError(reason.message))}>{saving ? 'Saving…' : 'Save project'}</button>
            <button disabled={busy || saving || !config.cards.length} onClick={() => exportProject('selected')}>Export selected set</button>
            <button className="primary" disabled={busy || saving || !config.cards.length} onClick={() => exportProject('all')}>Export full matrix</button>
          </div>
        </div>
      )}
    </header>

    {error && <section role="alert" className="mx-6 mt-4 p-4 bg-red-950/40 border border-red-400/30 rounded-xl whitespace-pre-wrap">
      {error}<div className="flex gap-3 mt-2"><button onClick={recoverDraft}>Download current draft</button>
        <button onClick={() => { if (!dirty || confirm('Reload the project? Download your draft first to preserve unsaved changes.')) location.reload(); }}>Reload project</button></div></section>}
    {notice && <p role="status" className="mx-6 mt-4 text-indigo-200">{notice}</p>}

    {creating ? (
      <form className="max-w-xl mx-auto p-8 space-y-5" onSubmit={async event => {
        event.preventDefault(); try { await save(); setTarget(state.current!.targets[0]); setLocale(state.current!.project.defaultLocale || 'en-US'); setCreating(false); } catch (reason) { setError((reason as Error).message); }
      }}>
        <fieldset disabled={saving} className="space-y-5">
          <h2 className="text-2xl font-semibold">Start with your real app</h2>
          <p className="text-white/60">Choose where your screenshots will appear, then bring your real captures. Everything stays in this project.</p>
          <label>Project ID<input required pattern="[A-Za-z0-9][A-Za-z0-9_-]*" value={config.project.id} onChange={event => edit(current => ({ ...current, project: { ...current.project, id: event.target.value } }))} /></label>
          <label>App name<input required value={config.project.name} onChange={event => edit(current => ({ ...current, project: { ...current.project, name: event.target.value } }))} /></label>
          <label>Bundle ID<input required value={config.project.bundleId} onChange={event => edit(current => ({ ...current, project: { ...current.project, bundleId: event.target.value } }))} /></label>
          <label>Languages (comma separated)<input required defaultValue={(config.project.locales || [defaultLocale]).join(', ')} onChange={event => { const locales = [...new Set(event.target.value.split(',').map(value => value.trim()).filter(Boolean))]; edit(current => ({ ...current, project: { ...current.project, locales, defaultLocale: locales[0] || 'en-US' } })); }} /></label>
          <fieldset><legend>Targets</legend><div className="grid grid-cols-2 gap-2 mt-2">{Object.entries(TARGET_DIMENSIONS).map(([id, dimensions]) => <label className="flex gap-2 items-center" key={id}>
            <input type="checkbox" checked={config.targets.includes(id as TargetDevice)} onChange={event => edit(current => ({ ...current, targets: event.target.checked ? [...current.targets, id as TargetDevice] : current.targets.filter(value => value !== id) }))} />{dimensions.displayName}</label>)}</div></fieldset>
          <button disabled={saving || !config.targets.length} className="primary" type="submit">Create project</button>
        </fieldset>
      </form>
    ) : (
      <>
        {/* Workspace: Lifecycle & Governance */}
        <div className="space-y-6 p-6 max-w-6xl mx-auto" style={{ display: workspaceMode === 'lifecycle' ? 'block' : 'none' }}>
        {/* Sub-Tabs Segmented Control */}
        <div className="flex flex-wrap items-center justify-between border-b border-white/10 pb-4 gap-4">
          <div>
            <h2 className="text-lg font-semibold text-white">Lifecycle & Asset Governance</h2>
            <p className="text-xs text-white/50">Candidate approval, release history, storage engine policies, and audit trails.</p>
          </div>
          <div className="flex bg-white/5 p-1 rounded-xl border border-white/10 text-xs">
            <button
              type="button"
              className={`flex items-center gap-1.5 px-4 py-1.5 rounded-lg font-medium transition ${
                lifecycleTab === 'approval'
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-white/60 hover:text-white'
              }`}
              onClick={() => setLifecycleTab('approval')}
            >
              <span>🎯 Release Approval & History</span>
            </button>
            <button
              type="button"
              className={`flex items-center gap-1.5 px-4 py-1.5 rounded-lg font-medium transition ${
                lifecycleTab === 'governance'
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-white/60 hover:text-white'
              }`}
              onClick={() => setLifecycleTab('governance')}
            >
              <span>⚙️ Storage & Governance</span>
            </button>
          </div>
        </div>

        {lifecycleTab === 'approval' ? (
          <div className="space-y-6">
            <section className="p-5 border border-white/10 rounded-xl bg-white/5" aria-label="Release review">
              <div className="flex justify-between items-center gap-4">
                <div>
                  <h3 className="font-semibold text-base text-white">Release Candidate Review</h3>
                  <p className="text-xs text-white/50">Zero-network Apple Store verification and rendering evidence.</p>
                </div>
                <button disabled={busy || saving} onClick={refreshStatus} className="text-xs">Check current files</button>
              </div>
              <p className="text-sm text-white/60 my-3">{verified ? 'All declared assets passed local checks. See publication verification for upload status.' : policyChecked ? 'Candidate checks passed under this project’s policy. Rendering evidence is not required by the current policy.' : 'Export and verify the full matrix before preparing a store handoff.'} Each export is saved as a separate production attempt in the configured workspace.</p>
              {!config.studio?.requireExportEvidence && <button disabled={busy || saving} onClick={() => {
                edit(current => ({ ...current, project: { ...current.project, id: current.project.id || 'my-app' }, studio: { ...current.studio, requireExportEvidence: true } }));
                if (!config.project.id || !config.project.name || !config.project.bundleId) setCreating(true);
              }}>Require rendering evidence</button>}
              {!dirty && errors.length > 0 && <ul className="text-sm text-amber-200 space-y-1 max-h-52 overflow-auto bg-amber-950/20 p-3 rounded-lg border border-amber-500/20 my-3">{errors.map((finding, index) => <li key={index}>⚠️ {finding}</li>)}</ul>}
              {!dirty && status.candidate_id && status.validation?.assets && Object.keys(status.validation.assets).length > 0 &&
                <ul className="grid grid-cols-2 md:grid-cols-3 gap-2 my-3 text-xs">{(config.project.locales || [defaultLocale]).flatMap(language => config.targets.flatMap(device => config.cards.map(card => {
                  const name = `${language}/${device}/${card.id}.png`;
                  return Object.hasOwn(status.validation!.assets, name) ? <li key={name} className="truncate"><a className="text-indigo-200 hover:text-indigo-100 underline" target="_blank" rel="noreferrer"
                    href={'/api/artifacts/' + encodeURIComponent(status.candidate_id || '') + '/' + name.split('/').map(encodeURIComponent).join('/')}>{language} · {TARGET_DIMENSIONS[device]?.displayName} · {card.id}</a></li> : null;
                })))}</ul>}
              {!dirty && status.candidate_id && status.validation?.assets &&
                <CandidatePreviewMedia candidateId={status.candidate_id} assets={status.validation.assets} />}
              {verified && <p className="text-sm text-emerald-300 mt-3 font-medium">✓ Next: ask your ASC agent to prepare the handoff, review these assets, and request separate upload approval.</p>}
            </section>
            {!dirty && status.candidate_id && <CandidateApproval key={status.candidate_id} candidateId={status.candidate_id} />}
            <div className="pt-4 border-t border-white/10">
              <h3 className="text-sm font-semibold text-white/70 mb-4 uppercase tracking-wider font-mono">Audit Trails & Publication Receipts</h3>
              <div className="space-y-6">
                <RunHistory />
                <DeliveryHistory />
                <PublicationHistory />
                <ObservationEvidence />
              </div>
            </div>
          </div>
        ) : (
          <div className="space-y-6">
            <ArchivePolicySettings policy={config.archivePolicy} budget={config.artifactPolicy?.mediaBudgetBytes} disabled={busy || saving}
              onChange={policy => edit(current => ({ ...current, archivePolicy: policy }))}
              onBudgetChange={budget => edit(current => {
                const policy = { ...current.artifactPolicy, schema_version: 1 as const };
                if (budget === undefined) delete policy.mediaBudgetBytes;
                else policy.mediaBudgetBytes = budget;
                return { ...current, artifactPolicy: policy };
              })} />
            <StorageSettings config={config} onChange={edit} report={storagePreview} error={storageError}
              checking={checkingStorage} disabled={busy || saving}
              onCheck={() => { void previewDirectories().catch(() => {}); }} />
            <div className="grid md:grid-cols-2 gap-6">
              <MediaBudgetPanel />
              <InventoryView />
            </div>
            <div className="pt-6 border-t border-white/10">
              <div className="mb-4">
                <h3 className="text-sm font-semibold text-amber-300 flex items-center gap-1.5">
                  <span>⚠️ Maintenance, Relocation & Recovery</span>
                </h3>
                <p className="text-xs text-white/50">Storage backend migration, fences, and quarantine disaster recovery actions.</p>
              </div>
              <div className="space-y-6">
                <MaintenancePanel />
                <RelocationMaintenance />
                <RelocationActions onStorageChange={() => { storageChanged.current = true; setError('Storage switching was requested. Check relocation status, then reload before saving or exporting.'); }} />
                <RelocationStatusPanel />
                <RelocationRecovery onStorageChange={() => { storageChanged.current = true; setError('Recovery was requested. Check operation status, then reload before saving or exporting.'); }} />
                <OperationHistory />
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Workspace: Canvas & Review */}
      <div style={{ display: workspaceMode === 'canvas' ? 'block' : 'none' }}>
        {/* Design Toolbar Bar */}
        <fieldset disabled={busy || saving} className="flex flex-wrap gap-4 px-6 py-3 border-b border-white/10 bg-white/5 items-center">
          <label className="text-xs font-medium flex items-center gap-1.5">
            <span className="text-white/60">Target:</span>
            <select value={target} onChange={event => setTarget(event.target.value as TargetDevice)} className="text-xs bg-[#1A1F2C] border border-white/15 rounded-lg px-2 py-1">
              {config.targets.map(id => <option key={id} value={id}>{TARGET_DIMENSIONS[id]?.displayName || id}</option>)}
            </select>
          </label>
          <label className="text-xs font-medium flex items-center gap-1.5">
            <span className="text-white/60">Language:</span>
            <select value={locale} onChange={event => setLocale(event.target.value)} className="text-xs bg-[#1A1F2C] border border-white/15 rounded-lg px-2 py-1">
              {(config.project.locales || ['en-US']).map(value => <option key={value}>{value}</option>)}
            </select>
          </label>
          <label className="text-xs font-medium flex items-center gap-1.5">
            <span className="text-white/60">Visual style:</span>
            <select value={config.theme.stylePreset || ''} onChange={event => edit(current => ({ ...current, theme: { ...current.theme, stylePreset: event.target.value } }))} className="text-xs bg-[#1A1F2C] border border-white/15 rounded-lg px-2 py-1">
              <option value="">Project theme</option>
              {Object.entries(STYLE_PRESETS).map(([id, preset]) => <option key={id} value={id}>{preset.name}</option>)}
            </select>
          </label>
          <label className="flex items-center gap-2 text-xs text-white/80 cursor-pointer ml-auto">
            <input type="checkbox" checked={!!config.connectedTrack} onChange={event => edit(current => ({ ...current, connectedTrack: event.target.checked }))} />
            Connected panorama track
          </label>
        </fieldset>

        {/* Narrow Viewport (Sidecar / Mobile) Tab Switcher */}
        <div className="flex lg:hidden border-b border-white/10 bg-[#0C0F17] px-4 py-2 gap-2 text-xs">
          <button
            type="button"
            className={`flex-1 py-1.5 rounded-lg font-medium transition ${canvasNarrowTab === 'cards' ? 'bg-indigo-600 text-white shadow-sm' : 'text-white/60 hover:text-white bg-white/5'}`}
            onClick={() => setCanvasNarrowTab('cards')}
          >
            📑 Cards ({config.cards.length})
          </button>
          <button
            type="button"
            className={`flex-1 py-1.5 rounded-lg font-medium transition ${canvasNarrowTab === 'canvas' ? 'bg-indigo-600 text-white shadow-sm' : 'text-white/60 hover:text-white bg-white/5'}`}
            onClick={() => setCanvasNarrowTab('canvas')}
          >
            🎨 Canvas
          </button>
          <button
            type="button"
            className={`flex-1 py-1.5 rounded-lg font-medium transition ${canvasNarrowTab === 'inspector' ? 'bg-indigo-600 text-white shadow-sm' : 'text-white/60 hover:text-white bg-white/5'}`}
            onClick={() => setCanvasNarrowTab('inspector')}
          >
            ⚙️ Inspector
          </button>
        </div>

        {/* 3-Column Studio Canvas */}
        <div className="grid lg:grid-cols-[260px_minmax(0,1fr)_340px] gap-0 min-h-[calc(100vh-140px)]">
          {/* Left Deck Rail */}
          <aside className={`p-4 space-y-3 border-r border-white/10 bg-[#0C0F17]/50 ${canvasNarrowTab === 'cards' ? 'block' : 'hidden'} lg:block`}>
            <div className="flex justify-between items-center">
              <h2 className="font-semibold text-sm">Screenshots · {config.cards.length}</h2>
              <span className="text-[10px] text-white/40 font-mono">5-Slide Arc</span>
            </div>
            <label className="upload text-xs block text-center py-2">Add real captures<input type="file" accept="image/png,image/jpeg" multiple disabled={busy || saving} onChange={event => { if (event.target.files) void importFiles(event.target.files); event.target.value = ''; }} /></label>
            <button className="w-full text-xs" disabled={busy || saving} onClick={() => { const id = `card-${crypto.randomUUID().slice(0, 8)}`; edit(current => ({ ...current, cards: [...current.cards, { id, headline: 'Your headline', layout: 'pure_text' }] })); setSelected(id); }}>Add text card</button>
            <ol className="space-y-1.5">{config.cards.map((card, index) => (
              <li key={card.id}>
                <button type="button" className={`w-full text-left p-2.5 rounded-xl border text-xs flex flex-col gap-1 transition ${selected === card.id ? 'border-indigo-400 bg-indigo-500/15 shadow-sm ring-1 ring-indigo-400/30' : 'border-white/10 hover:border-white/20 bg-white/5'}`} onClick={() => { setSelected(card.id); setCanvasNarrowTab('canvas'); }}>
                  <div className="flex justify-between items-center text-white/50 text-[10px] font-mono">
                    <span>CARD {String(index + 1).padStart(2, '0')}</span>
                    <span className="uppercase text-indigo-300 bg-indigo-500/20 px-1 rounded text-[9px] border border-indigo-500/30">{getCardRole(index)}</span>
                  </div>
                  <div className="font-medium text-white truncate">{resolveCard(config, card, target, locale).headline || 'Untitled'}</div>
                </button>
              </li>
            ))}</ol>
            <p className="text-[11px] text-white/40">{total} outputs declared. Each language and target needs reviewed copy and real source captures.</p>
          </aside>

          {/* Center Stage Preview Area */}
          <section className={`overflow-auto p-8 min-h-[500px] flex items-center justify-start bg-gradient-to-b from-black/20 to-black/60 relative ${canvasNarrowTab === 'canvas' ? 'flex' : 'hidden'} lg:flex`} aria-label="Screenshot previews"
            onDragOver={event => event.preventDefault()} onDrop={event => { event.preventDefault(); if (!busy && !saving) void importFiles(event.dataTransfer.files); }}>
            {!config.cards.length ? (
              <div className="p-12 text-center border border-dashed border-white/20 rounded-2xl max-w-md m-auto">
                <h2 className="text-xl mb-3 font-semibold">Bring your real app screens</h2>
                <p className="text-white/60 text-sm">Drop PNG or JPEG captures here. Select the intended target and language before importing.</p>
              </div>
            ) : (
              <div className="flex gap-8 items-start py-4 m-auto">
                {config.cards.map((card, index) => (
                  <div key={card.id} className={`shrink-0 cursor-pointer transition-all duration-200 hover:scale-[1.01] rounded-2xl ${
                    selected === card.id ? 'ring-2 ring-blue-500 shadow-2xl shadow-blue-500/20' : 'ring-1 ring-white/10'
                  }`} onClick={() => setSelected(card.id)}>
                    <CardView card={resolveCard(config, card, target, locale)} index={index} totalCards={config.cards.length}
                      target={target} theme={config.theme} locale={locale} connected={config.connectedTrack}
                      onUpdateText={(field, value) => edit(current => updateVariant(current, card.id, target, locale, { [field]: value }))}
                      onReview={findings => { const key = `${target}/${locale}/${card.id}`, value = findings.join('. ');
                        setLayoutFindings(current => current[key] === value ? current : { ...current, [key]: value }); }} />
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* Right Inspector Panel */}
          <aside className={`p-4 border-l border-white/10 bg-[#0C0F17]/50 flex flex-col overflow-y-auto ${canvasNarrowTab === 'inspector' ? 'flex' : 'hidden'} lg:flex`}>
            {active && resolved ? (
              <fieldset disabled={busy || saving} className="space-y-4">
                <div className="flex items-center justify-between pb-2 border-b border-white/10">
                  <div>
                    <h2 className="font-semibold text-sm">Inspector</h2>
                    <p className="text-[11px] text-white/50">{TARGET_DIMENSIONS[target]?.displayName} · {locale}</p>
                  </div>
                  <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                    {getCardRole(config.cards.findIndex(c => c.id === active.id))}
                  </span>
                </div>

                {/* 4 Tabs */}
                <div className="flex border-b border-white/10 text-xs gap-1">
                  <button type="button" className={`flex-1 py-1.5 border-b-2 font-medium transition ${inspectorTab === 'copy' ? 'border-indigo-500 text-indigo-300' : 'border-transparent text-white/60 hover:text-white'}`}
                    onClick={() => setInspectorTab('copy')}>Copy</button>
                  <button type="button" className={`flex-1 py-1.5 border-b-2 font-medium transition ${inspectorTab === 'spatial' ? 'border-indigo-500 text-indigo-300' : 'border-transparent text-white/60 hover:text-white'}`}
                    onClick={() => setInspectorTab('spatial')}>3D Spatial</button>
                  <button type="button" className={`flex-1 py-1.5 border-b-2 font-medium transition ${inspectorTab === 'ambiance' ? 'border-indigo-500 text-indigo-300' : 'border-transparent text-white/60 hover:text-white'}`}
                    onClick={() => setInspectorTab('ambiance')}>Ambiance</button>
                  <button type="button" className={`flex-1 py-1.5 border-b-2 font-medium transition ${inspectorTab === 'review' ? 'border-indigo-500 text-indigo-300' : 'border-transparent text-white/60 hover:text-white'}`}
                    onClick={() => setInspectorTab('review')}>Review</button>
                </div>

                {/* TAB 1: COPY */}
                {inspectorTab === 'copy' && (
                  <div className="space-y-3">
                    {inherited && (
                      <div className="p-2.5 bg-amber-950/40 border border-amber-300/20 rounded-xl text-xs">
                        Copy or capture inherits the default language.
                        <label className="flex gap-2 mt-1.5"><input type="checkbox" checked={!!fields.inheritDefault} onChange={event => mutate({ inheritDefault: event.target.checked })} />I reviewed the inherited content</label>
                      </div>
                    )}
                    <div className="space-y-1">
                      <div className="flex justify-between items-center">
                        <label className="text-xs font-medium text-white/80">Headline</label>
                        <button type="button" className="text-[11px] text-amber-300 hover:text-amber-200" onClick={() => setShowCopyIdeas(!showCopyIdeas)}>💡 Copy Ideas</button>
                      </div>
                      {showCopyIdeas && (
                        <div className="p-2 bg-[#141824] border border-indigo-500/30 rounded-xl max-h-48 overflow-y-auto space-y-1.5 text-xs shadow-xl">
                          <div className="text-[10px] uppercase font-mono text-white/40">Marketing Playbook Formulas</div>
                          {COPY_FORMULAS.map((f, i) => (
                            <div key={i} className="p-1.5 rounded hover:bg-white/10 cursor-pointer transition"
                              onClick={() => { mutate({ headline: f.headline, subheadline: f.subheadline }); setShowCopyIdeas(false); }}>
                              <div className="font-semibold text-white flex justify-between">
                                <span>{f.headline}</span>
                                <span className="text-[9px] text-indigo-300">{f.role}</span>
                              </div>
                              <div className="text-[11px] text-white/60 line-clamp-1">{f.subheadline}</div>
                            </div>
                          ))}
                        </div>
                      )}
                      <textarea rows={2} value={resolved.headline} onChange={event => mutate({ headline: event.target.value })} className="w-full text-xs" />
                    </div>
                    <div className="space-y-1">
                      <label className="text-xs font-medium text-white/80">Subheadline</label>
                      <textarea rows={2} value={resolved.subheadline || ''} onChange={event => mutate({ subheadline: event.target.value })} className="w-full text-xs" />
                    </div>
                    <div className="space-y-1">
                      <label className="text-xs font-medium text-white/80">Composition</label>
                      <select value={resolved.layout || defaultCardLayout(target)} onChange={event => mutate({ layout: event.target.value as CardConfig['layout'] })} className="w-full text-xs">
                        {layouts.map(value => <option key={value} value={value}>{layoutName(value)}</option>)}
                      </select>
                    </div>
                    {resolved.screenshot ? (
                      <img className="max-h-24 mx-auto rounded object-contain border border-white/10" src={resolved.screenshot} alt="Assigned real capture" />
                    ) : (
                      <p className="text-amber-200 text-xs">{resolved.layout === 'pure_text' ? 'Text-only composition.' : 'No capture assigned.'}</p>
                    )}
                    <label className="upload text-xs block text-center">Replace capture for {locale}<input type="file" accept="image/png,image/jpeg" onChange={event => { if (event.target.files) void importFiles(event.target.files, true); event.target.value = ''; }} /></label>
                    <div className="flex gap-2">
                      <button type="button" className="flex-1 text-xs" disabled={config.cards[0]?.id === active.id} onClick={() => edit(current => { const cards = [...current.cards]; const index = cards.findIndex(c => c.id === active.id); [cards[index - 1], cards[index]] = [cards[index], cards[index - 1]]; return { ...current, cards }; })}>Move earlier</button>
                      <button type="button" className="flex-1 text-xs" disabled={config.cards.at(-1)?.id === active.id} onClick={() => edit(current => { const cards = [...current.cards]; const index = cards.findIndex(c => c.id === active.id); [cards[index + 1], cards[index]] = [cards[index], cards[index + 1]]; return { ...current, cards }; })}>Move later</button>
                    </div>
                    <button type="button" className="w-full text-xs text-red-300 hover:text-red-200" onClick={() => { if (confirm('Remove this screenshot from the set?')) { edit(current => ({ ...current, cards: current.cards.filter(c => c.id !== active.id) })); setSelected(''); } }}>Remove screenshot</button>
                  </div>
                )}

                {/* TAB 2: 3D SPATIAL & PERSPECTIVE */}
                {inspectorTab === 'spatial' && (
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-medium text-white/80">Pose Presets</span>
                      <button type="button" className="text-[10px] text-white/40 hover:text-white" onClick={() => applyPresetPose('flat')}>Reset</button>
                    </div>
                    {(() => {
                      const pose = classifyPose(resolved?.deviceOffset);
                      const isHero = pose === 'hero';
                      const isGaze = pose === 'gaze';
                      const isGrounded = pose === 'grounded';
                      const activeCls = "py-1 px-1.5 text-[11px] rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 font-medium";
                      const inactiveCls = "py-1 px-1.5 text-[11px] rounded bg-white/5 hover:bg-white/10 border border-white/10 text-white/70";
                      return (
                        <div className="grid grid-cols-3 gap-1.5 text-xs">
                          <button type="button" className={isHero ? activeCls : inactiveCls} onClick={() => applyPresetPose('hero')}>Hero 3D</button>
                          <button type="button" className={isGaze ? activeCls : inactiveCls} onClick={() => applyPresetPose('gaze')}>Inward Yaw</button>
                          <button type="button" className={isGrounded ? activeCls : inactiveCls} onClick={() => applyPresetPose('grounded')}>Grounded</button>
                        </div>
                      );
                    })()}

                    {layoutFindings[`${target}/${locale}/${active.id}`] && (
                      <div className="p-2 rounded bg-amber-950/40 border border-amber-500/30 text-[11px] text-amber-200">
                        ⚠️ {layoutFindings[`${target}/${locale}/${active.id}`]}
                      </div>
                    )}

                    {/* Pitch / rotateX */}
                    <div>
                      <div className="flex justify-between text-xs text-white/70">
                        <span>Pitch / 俯仰 (rotateX)</span>
                        <span className="font-mono text-indigo-300">{resolved.deviceOffset?.rotateX ?? 0}°</span>
                      </div>
                      <input type="range" min="-15" max="25" step="1" value={resolved.deviceOffset?.rotateX ?? 0}
                        onChange={e => updateOffset({ rotateX: Number(e.target.value) })} className="w-full cursor-pointer accent-indigo-500" />
                    </div>

                    {/* Yaw / 偏航 (rotateY) */}
                    <div>
                      <div className="flex justify-between text-xs text-white/70">
                        <span>Yaw / 偏航 (rotateY)</span>
                        <span className="font-mono text-indigo-300">{resolved.deviceOffset?.rotateY ?? 0}°</span>
                      </div>
                      <input type="range" min="-20" max="20" step="1" value={resolved.deviceOffset?.rotateY ?? 0}
                        onChange={e => updateOffset({ rotateY: Number(e.target.value) })} className="w-full cursor-pointer accent-indigo-500" />
                    </div>

                    {/* Roll / 平面旋转 (rotate) */}
                    <div>
                      <div className="flex justify-between text-xs text-white/70">
                        <span>Roll / 旋转 (rotate)</span>
                        <span className="font-mono text-indigo-300">{resolved.deviceOffset?.rotate ?? 0}°</span>
                      </div>
                      <input type="range" min="-15" max="15" step="0.5" value={resolved.deviceOffset?.rotate ?? 0}
                        onChange={e => updateOffset({ rotate: Number(e.target.value) })} className="w-full cursor-pointer accent-indigo-500" />
                    </div>

                    {/* Scale / 缩放 */}
                    <div>
                      <div className="flex justify-between text-xs text-white/70">
                        <span>Scale / 比例</span>
                        <span className="font-mono text-indigo-300">{(resolved.deviceOffset?.scale ?? 1.0).toFixed(2)}x</span>
                      </div>
                      <input type="range" min="0.70" max="1.30" step="0.01" value={resolved.deviceOffset?.scale ?? 1.0}
                        onChange={e => updateOffset({ scale: Number(e.target.value) })} className="w-full cursor-pointer accent-indigo-500" />
                    </div>

                    {/* X and Y Offsets */}
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <div className="flex justify-between text-xs text-white/70">
                          <span>Offset X</span>
                          <span className="font-mono text-indigo-300">{resolved.deviceOffset?.x ?? 0}px</span>
                        </div>
                        <input type="range" min="-100" max="100" step="1" value={resolved.deviceOffset?.x ?? 0}
                          onChange={e => updateOffset({ x: Number(e.target.value) })} className="w-full cursor-pointer accent-indigo-500" />
                      </div>
                      <div>
                        <div className="flex justify-between text-xs text-white/70">
                          <span>Offset Y</span>
                          <span className="font-mono text-indigo-300">{resolved.deviceOffset?.y ?? 0}px</span>
                        </div>
                        <input type="range" min="-100" max="100" step="1" value={resolved.deviceOffset?.y ?? 0}
                          onChange={e => updateOffset({ y: Number(e.target.value) })} className="w-full cursor-pointer accent-indigo-500" />
                      </div>
                    </div>
                  </div>
                )}

                {/* TAB 3: AMBIANCE & LIGHTING */}
                {inspectorTab === 'ambiance' && (
                  <div className="space-y-3">
                    <div className="space-y-1">
                      <label className="text-xs font-medium text-white/80">Visual Theme Preset</label>
                      <select value={config.theme.stylePreset || ''} onChange={event => edit(current => ({ ...current, theme: { ...current.theme, stylePreset: event.target.value } }))} className="w-full text-xs">
                        <option value="">Project theme</option>
                        {Object.entries(STYLE_PRESETS).map(([id, preset]) => <option key={id} value={id}>{preset.name}</option>)}
                      </select>
                    </div>

                    <div className="space-y-1">
                      <div className="flex justify-between text-xs text-white/70">
                        <span>Gradient Lighting Angle</span>
                        <span className="font-mono text-indigo-300">{config.theme.background?.angle ?? 135}°</span>
                      </div>
                      <input type="range" min="0" max="360" step="5" value={config.theme.background?.angle ?? 135}
                        onChange={e => edit(current => ({ ...current, theme: { ...current.theme, background: { ...current.theme.background, angle: Number(e.target.value) } } }))}
                        className="w-full cursor-pointer accent-indigo-500" />
                    </div>

                    <label className="flex items-center gap-2 text-xs text-white/80 cursor-pointer pt-2">
                      <input type="checkbox" checked={!!config.connectedTrack} onChange={event => edit(current => ({ ...current, connectedTrack: event.target.checked }))} />
                      Connected Panorama Track
                    </label>
                  </div>
                )}

                {/* TAB 4: AGENT REVIEW LOOP */}
                {inspectorTab === 'review' && (
                  <div className="space-y-3">
                    <div>
                      <label className="text-xs font-medium text-white/80">Human Critique & Directive</label>
                      <p className="text-[10px] text-white/50">Write review notes for autonomous Agent digestion</p>
                    </div>
                    <textarea rows={3} placeholder="E.g. Tilt window 3° right, adjust headline to focus on clipboard speed..."
                      value={active ? (critiqueNotesByCard[active.id] || '') : ''}
                      onChange={e => {
                        const val = e.target.value;
                        if (active) {
                          setCritiqueNotesByCard(prev => ({ ...prev, [active.id]: val }));
                          setDirtyCritiqueCards(prev => ({ ...prev, [active.id]: true }));
                        }
                      }} className="w-full text-xs" />
                    <div className="flex flex-col gap-2 pt-1">
                      <button type="button" className="primary text-xs flex items-center justify-center gap-1.5"
                        disabled={syncingCritique} onClick={syncCritique}>
                        <span>⚡ Sync Directives to Agent</span>
                      </button>
                      <button type="button" className="text-xs flex items-center justify-center gap-1.5"
                        onClick={copyCritiqueMarkdown}>
                        <span>📋 Copy Markdown Directive</span>
                      </button>
                    </div>
                    {critiqueNotice && (
                      <p role="status" className="text-xs text-emerald-300">{critiqueNotice}</p>
                    )}
                  </div>
                )}
              </fieldset>
            ) : (
              <p className="text-white/50 text-xs">Select a screenshot to adjust its copy, 3D spatial properties, or agent critique.</p>
            )}
          </aside>
        </div>
      </div>
    </>
  )}
</main>;
};
