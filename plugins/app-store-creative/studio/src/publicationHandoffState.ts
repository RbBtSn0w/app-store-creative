export type PublicationTarget = Record<string, unknown> & { app_id: string; platform: string };

export function validPublicationTarget(input: unknown): input is PublicationTarget {
  if (!input || typeof input !== 'object' || Array.isArray(input)) return false;
  const target = input as Record<string, unknown>;
  const has = (key: string) => typeof target[key] === 'string' && Boolean(target[key].trim());
  if (!has('app_id') || !has('platform')) return false;
  if (target.kind === 'customProductPageVersion') {
    return target.platform === 'IOS' && !('version_id' in target)
      && ['bundle_id', 'page_id', 'page_version_id', 'cpp_localization_id', 'locale', 'target', 'display_type'].every(has)
      && typeof target.plan_digest === 'string' && /^[a-f0-9]{64}$/.test(target.plan_digest)
      && Array.isArray(target.ordered_assets) && target.ordered_assets.length > 0
      && target.set_ids !== null && typeof target.set_ids === 'object' && !Array.isArray(target.set_ids)
      && Object.entries(target.set_ids).every(([role, id]) =>
        ['screenshot', 'preview'].includes(role) && typeof id === 'string' && id.trim().length > 0);
  }
  return (target.kind === undefined || target.kind === 'appStoreVersion') && has('version_id')
    && !['page_id', 'page_version_id', 'cpp_localization_id'].some(key => key in target)
    && Object.values(target).every(item => typeof item === 'string');
}

export type HandoffPreview = { publication_id: string; plan_sha256: string; upload_approval: string; uploaded: boolean; remote_write: boolean; handoff: { id: string; target: PublicationTarget; assets: { artifact_id: string; role: string; sha256: string; path: string }[] } };
export function parseHandoffPreview(value: unknown, id: string): HandoffPreview {
  const preview = value as HandoffPreview;
  if (!preview || preview.publication_id !== id || !/^[0-9a-f]{64}$/.test(preview.plan_sha256) || !preview.handoff?.target || !Array.isArray(preview.handoff.assets)) throw new Error('Invalid handoff review');
  if (preview.uploaded !== false || preview.remote_write !== false || !['approved', 'pending'].includes(preview.upload_approval)
      || preview.handoff.id !== id || !validPublicationTarget(preview.handoff.target) || preview.handoff.assets.length === 0) throw new Error('Incomplete handoff scope');
  const identities = new Set<string>();
  for (const asset of preview.handoff.assets) {
    if (!asset || typeof asset !== 'object' || typeof asset.artifact_id !== 'string' || !/^[a-z0-9]+$/.test(asset.artifact_id)
        || typeof asset.role !== 'string' || !asset.role.trim() || typeof asset.path !== 'string' || !asset.path.trim()
        || !/^[0-9a-f]{64}$/.test(asset.sha256) || identities.has(asset.artifact_id)) throw new Error('Invalid handoff asset');
    identities.add(asset.artifact_id);
  }
  const target = preview.handoff.target;
  if (target.kind === 'customProductPageVersion') {
    const ordered = target.ordered_assets;
    if (!Array.isArray(ordered) || ordered.length !== preview.handoff.assets.length ||
      !ordered.every((item, index) => {
        const asset = preview.handoff.assets[index];
        return item?.artifactId === asset.artifact_id && item.sha256 === asset.sha256 && item.role === asset.role;
      })) throw new Error('CPP handoff differs from the reviewed media order');
  }
  return preview;
}
