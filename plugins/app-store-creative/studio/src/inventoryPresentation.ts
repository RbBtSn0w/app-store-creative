export type InventoryCopy = {
  id?: string; relocation_id?: string; path: string; status: string; phase?: string; kind?: string;
  observed_logical_bytes?: number | null; expected_logical_bytes?: number;
  extra_files?: string[]; missing_files?: string[]; changed_files?: string[]; unsafe_links?: string[];
  identity_conflicts?: string[]; unregistered_payloads?: string[]; purged_files?: string[];
};
type Finding = { id?: string; relocation_id?: string; reason: string };
const objectFindings = ['corrupt', 'missing', 'orphan_files', 'unknown_files', 'unknown_quarantine_files',
  'corrupt_quarantine_files', 'unsafe_links'] as const;
export type Inventory = {
  objects: { reference_count: number; registered_identities: number; active_count: number | null; unobserved_registered: string[]; quarantined: string[]; purged: string[] }
    & Record<typeof objectFindings[number], string[]>;
  capacity: Record<string, number | string | null>;
  other_unsafe_links: string[];
  observation_errors: { area: string; path: string; reason: string }[];
  relocation_backups: { copies: InventoryCopy[]; staging: InventoryCopy[]; unverified_operations: Finding[]; disposition_errors?: Finding[] };
  quarantine_preparations: { operations: InventoryCopy[]; unverified_operations: Finding[] };
};

export function formatInventoryBytes(value: number | null | undefined): string {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 0) return 'Not measured';
  if (value === 0) return '0 B';
  const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB'];
  const index = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
  return `${Number((value / 1024 ** index).toFixed(index ? 1 : 0))} ${units[index]}`;
}

export function inventoryStatus(status: string): string {
  const labels: Record<string, string> = {
    VERIFIED: 'Files match', CHANGED: 'Files differ', MISSING: 'Files missing', PARTIAL: 'Partial output',
    IDENTITY_CONFLICT: 'File or directory replaced', UNSAFE: 'Unsafe location', UNVERIFIED_OWNERSHIP: 'Ownership unverified',
    PREPARED: 'Preparation complete', PREPARING: 'Preparation in progress', INTERRUPTED: 'Preparation interrupted',
    CANCELLED: 'Preparation cancelled', CANCELLED_PARTIAL: 'Preparation partly cancelled',
    QUARANTINED: 'Copies isolated', COMMIT_STARTED: 'Isolation started', RESTORING: 'Restoration in progress',
    RESTORED: 'Copies restored', PURGING: 'Deletion in progress', PURGED: 'Copies deleted',
    PARTIALLY_PURGED: 'Copies partly deleted', ACTIVE_CONFLICT: 'Location is active',
  };
  return labels[status] || `Unrecognized status: ${status}`;
}

const record = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);
const strings = (value: unknown) => Array.isArray(value) && value.every(item => typeof item === 'string');
const count = (value: unknown) => typeof value === 'number' && Number.isSafeInteger(value) && value >= 0;
export function parseInventory(value: unknown): Inventory {
  function require(condition: unknown): asserts condition { if (!condition) throw new Error('Incomplete inventory response. Check again.'); }
  require(record(value));
  require(record(value.objects) && record(value.capacity) && strings(value.other_unsafe_links));
  const objects = value.objects;
  for (const field of [...objectFindings, 'quarantined', 'purged', 'unobserved_registered']) require(strings(objects[field]));
  for (const field of ['reference_count', 'registered_identities']) require(count(objects[field]));
  require(objects.active_count === null || count(objects.active_count));
  require(Array.isArray(value.observation_errors));
  for (const error of value.observation_errors) require(record(error) &&
    typeof error.area === 'string' && typeof error.path === 'string' && typeof error.reason === 'string');
  for (const field of ['active_object_bytes', 'quarantine_file_bytes', 'other_object_file_bytes', 'work_file_bytes',
    'release_directory_bytes', 'publication_directory_bytes', 'git_history_bytes', 'lfs_remote_bytes', 'external_backend_bytes']) {
    require(value.capacity[field] === null || count(value.capacity[field]));
  }
  const copies = (items: unknown) => {
    require(Array.isArray(items));
    for (const item of items) {
      require(record(item) && typeof item.path === 'string' && typeof item.status === 'string');
      require(typeof item.id === 'string' || typeof item.relocation_id === 'string');
      require(item.phase === undefined || typeof item.phase === 'string');
      require(item.observed_logical_bytes === null || item.observed_logical_bytes === undefined || count(item.observed_logical_bytes));
      for (const key of ['extra_files', 'missing_files', 'changed_files', 'unsafe_links', 'identity_conflicts', 'unregistered_payloads', 'purged_files']) {
        require(item[key] === undefined || strings(item[key]));
      }
    }
  };
  const findings = (items: unknown) => {
    require(Array.isArray(items));
    for (const item of items) require(record(item) && typeof item.reason === 'string');
  };
  require(record(value.relocation_backups) && record(value.quarantine_preparations));
  copies(value.relocation_backups.copies); copies(value.relocation_backups.staging); copies(value.quarantine_preparations.operations);
  findings(value.relocation_backups.unverified_operations); findings(value.quarantine_preparations.unverified_operations);
  if (value.relocation_backups.disposition_errors !== undefined) findings(value.relocation_backups.disposition_errors);
  return value as Inventory;
}
