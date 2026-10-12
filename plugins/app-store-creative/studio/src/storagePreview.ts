import type { CreativeConfig } from './types';

export const storageRoots = [
  ['workspaceRoot', 'Working files', '.creative'],
  ['objectRoot', 'Media objects', 'Working directory / objects'],
  ['releaseRoot', 'Release archives', 'creative-releases'],
  ['publicationRoot', 'Publication records', 'creative-publications'],
] as const;
export type StorageRoot = typeof storageRoots[number][0];
type RootPreview = { configured: string | null; source: 'local' | 'project' | 'default' | 'derived'; resolved: string };
export type StoragePreview = { binding: Record<string, string>; roots: Record<StorageRoot, RootPreview>;
  roots_changed: boolean; requires_relocation: boolean; project_identity_conflict: boolean;
  configuration_path: string | null; writes_performed: false };

export function parseStoragePreview(value: unknown): StoragePreview {
  const data = value as StoragePreview;
  if (!data || typeof data !== 'object' || data.writes_performed !== false ||
      ['roots_changed', 'requires_relocation', 'project_identity_conflict'].some(key => typeof (data as unknown as Record<string, unknown>)[key] !== 'boolean') ||
      !(data.configuration_path === null || typeof data.configuration_path === 'string')) throw new Error('Directory preview response is incomplete. Try again.');
  const bindings = ['workspace', 'objects', 'releases', 'publications'];
  for (const [index, [key]] of storageRoots.entries()) {
    const root = data.roots?.[key];
    if (!root || typeof root.resolved !== 'string' || !root.resolved.startsWith('/') ||
        data.binding?.[bindings[index]] !== root.resolved ||
        !['local', 'project', 'default', 'derived'].includes(root.source) ||
        !(root.configured === null || typeof root.configured === 'string')) throw new Error('Invalid directory preview response. Try again.');
  }
  return data;
}

export function changeStorageRoot(config: CreativeConfig, key: StorageRoot, value: string): CreativeConfig {
  const storage = { ...config.storage };
  if (value === '') delete storage[key]; else storage[key] = value;
  return { ...config, storage };
}

export function storageSaveConflict(report: StoragePreview): string | null {
  if (report.project_identity_conflict) return 'This workspace already belongs to the saved project identity. Keep its project ID.';
  if (report.requires_relocation) return 'Existing managed files require an explicit storage migration before saving these directories. Your draft is preserved.';
  return null;
}

export async function loadStoragePreview(config: CreativeConfig): Promise<StoragePreview> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 20000);
  try {
    const response = await fetch('/api/storage/preview', { method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({config}), signal:controller.signal });
    const body = await response.json();
    if (!response.ok) throw new Error(body.error || 'Could not preview directories. Try again.');
    return parseStoragePreview(body);
  } catch (error) {
    if (controller.signal.aborted) throw new Error('Directory preview timed out. Try again.');
    throw error;
  } finally { clearTimeout(timer); }
}
