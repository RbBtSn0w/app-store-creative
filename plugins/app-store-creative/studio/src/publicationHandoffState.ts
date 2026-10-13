export type HandoffPreview = { publication_id: string; plan_sha256: string; upload_approval: string; uploaded: boolean; remote_write: boolean; handoff: { id: string; target: Record<string, string>; assets: { artifact_id: string; role: string; sha256: string; path: string }[] } };
export function parseHandoffPreview(value: unknown, id: string): HandoffPreview {
  const preview = value as HandoffPreview;
  if (!preview || preview.publication_id !== id || !/^[0-9a-f]{64}$/.test(preview.plan_sha256) || !preview.handoff?.target || !Array.isArray(preview.handoff.assets)) throw new Error('Invalid handoff review');
  if (preview.uploaded !== false || preview.remote_write !== false || !['approved', 'pending'].includes(preview.upload_approval)
      || preview.handoff.id !== id || typeof preview.handoff.target !== 'object'
      || ['app_id', 'version_id', 'platform'].some(key => typeof preview.handoff.target[key] !== 'string' || !preview.handoff.target[key].trim())
      || Object.values(preview.handoff.target).some(item => typeof item !== 'string') || preview.handoff.assets.length === 0) throw new Error('Incomplete handoff scope');
  const identities = new Set<string>();
  for (const asset of preview.handoff.assets) {
    if (!asset || typeof asset !== 'object' || typeof asset.artifact_id !== 'string' || !/^[a-z0-9]+$/.test(asset.artifact_id)
        || typeof asset.role !== 'string' || !asset.role.trim() || typeof asset.path !== 'string' || !asset.path.trim()
        || !/^[0-9a-f]{64}$/.test(asset.sha256) || identities.has(asset.artifact_id)) throw new Error('Invalid handoff asset');
    identities.add(asset.artifact_id);
  }
  return preview;
}
