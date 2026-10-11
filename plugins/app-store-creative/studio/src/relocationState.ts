const roots = ['workspace', 'objects', 'releases', 'publications'];
export type RelocationPlan = {
  id: string; operation: string; from: Record<string, string>; to: Record<string, string>;
  files: { root: string; path: string; sha256: string; size_bytes: number }[]; logical_bytes: number;
};
export function parseRelocationPlan(value: unknown): RelocationPlan {
  if (!value || typeof value !== 'object') throw new Error('Invalid relocation plan');
  const plan = value as RelocationPlan;
  if (typeof plan.id !== 'string' || !/^[a-z0-9]+$/.test(plan.id) || !['relocation-plan', 'reverse-relocation-plan'].includes(plan.operation)
      || !Array.isArray(plan.files) || !Number.isSafeInteger(plan.logical_bytes) || plan.logical_bytes < 0) throw new Error('Invalid relocation identity');
  for (const binding of [plan.from, plan.to]) {
    if (!binding || typeof binding !== 'object' || Object.keys(binding).length !== roots.length
        || roots.some(root => typeof binding[root] !== 'string' || !binding[root].startsWith('/') || /[\u0000-\u001f]/.test(binding[root]))) throw new Error('Incomplete relocation directories');
  }
  const paths = new Set<string>(); let total = 0;
  for (const file of plan.files) {
    if (!file || typeof file !== 'object' || !roots.includes(file.root) || typeof file.path !== 'string'
        || file.path.startsWith('/') || file.path.split('/').some(part => !part || part === '.' || part === '..')
        || /[\u0000-\u001f]/.test(file.path) || !/^[0-9a-f]{64}$/.test(file.sha256)
        || !Number.isSafeInteger(file.size_bytes) || file.size_bytes < 0) throw new Error('Invalid relocation file');
    const key = file.root + '/' + file.path;
    if (paths.has(key)) throw new Error('Duplicate relocation file');
    paths.add(key); total += file.size_bytes;
    if (!Number.isSafeInteger(total)) throw new Error('Relocation size exceeds safe review range');
  }
  if (total !== plan.logical_bytes) throw new Error('Relocation size differs from the file list');
  return plan;
}
