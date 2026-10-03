export function downloadDraft(draft: unknown): void {
  const link = document.createElement('a');
  const url = URL.createObjectURL(new Blob([JSON.stringify(draft, null, 2)], { type: 'application/json' }));
  link.href = url;
  link.download = 'creative-draft.json';
  document.body.appendChild(link);
  try { link.click(); }
  finally {
    // Keep the URL live while the browser dispatches the download.
    setTimeout(() => { URL.revokeObjectURL(url); link.remove(); }, 0);
  }
}
