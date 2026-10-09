import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it } from 'vitest';
import { InventoryReport, InventoryView } from './InventoryView';
import { parseInventory } from './inventoryPresentation';

function specimen() {
  return {
    objects: { reference_count: 0, registered_identities: 0, active_count: 0,
      corrupt: [], missing: [], orphan_files: [], unknown_files: [], unknown_quarantine_files: [],
      corrupt_quarantine_files: [], unsafe_links: [], quarantined: [], purged: [], unobserved_registered: [] },
    capacity: { active_object_bytes: 0, quarantine_file_bytes: 0, other_object_file_bytes: 0, work_file_bytes: 0,
      release_directory_bytes: 0, publication_directory_bytes: 0, git_history_bytes: null, lfs_remote_bytes: null, external_backend_bytes: null },
    other_unsafe_links: [], observation_errors: [],
    relocation_backups: { copies: [], staging: [], unverified_operations: [] },
    quarantine_preparations: { operations: [], unverified_operations: [] },
  };
}
it('renders an explicit check before making any storage claim', () => {
  const html = renderToStaticMarkup(<InventoryView />);
  expect(html).toContain('Check storage'); expect(html).not.toContain('registered assets'); expect(html).not.toContain('No media exceptions');
});
it('renders an observed empty inventory without inferring remote storage', () => {
  const html = renderToStaticMarkup(<InventoryReport inventory={parseInventory(specimen())} />);
  expect(html).toContain('0 registered assets'); expect(html).toContain('0 B');
  expect(html).toContain('remote storage and external storage are not measured');
});
it('renders cancellation and damaged content independently, with unknown size retained', () => {
  const inventory = parseInventory({ ...specimen(), quarantine_preparations: { operations: [{id:'operation-1', path:'/retained/copies',
    phase:'CANCELLED', status:'CHANGED', observed_logical_bytes:null, changed_files:['preview.mp4'], extra_files:['owner-notes']}], unverified_operations:[] } });
  const html = renderToStaticMarkup(<InventoryReport inventory={inventory} />);
  for (const text of ['Preparation cancelled', 'Files differ', 'Not measured', 'preview.mp4', 'owner-notes']) expect(html).toContain(text);
  expect(html).not.toContain('Files match');
});
it('preserves operation verification failures and their reasons', () => {
  const data = specimen();
  const inventory = parseInventory({ ...data, relocation_backups: { ...data.relocation_backups,
    unverified_operations: [{relocation_id:'move-1', reason:'Switch receipt differs'}] } });
  const html = renderToStaticMarkup(<InventoryReport inventory={inventory} />);
  expect(html).toContain('Operations needing verification'); expect(html).toContain('Switch receipt differs');
});

it('reports unreadable storage as unknown rather than empty or healthy', () => {
  const data = specimen();
  const inventory = parseInventory({ ...data, objects: { ...data.objects, active_count: null, unobserved_registered: ['media-1'] },
    capacity: { ...data.capacity, active_object_bytes: null },
    observation_errors: [{area:'objects', path:'/media', reason:'Permission denied'}] });
  const html = renderToStaticMarkup(<InventoryReport inventory={inventory} />);
  for (const text of ['Local object count not observed', 'Not measured', 'Storage could not be fully checked', 'Permission denied', 'Media not observed']) expect(html).toContain(text);
  expect(html).not.toContain('No media exceptions');
  expect(html).not.toContain('0 observed local objects');
  expect(html).not.toContain('0 media objects isolated');
  expect(html).toContain('Isolation and deletion presence not observed');
});
