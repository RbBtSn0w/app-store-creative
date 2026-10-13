export async function maintenanceRequest(path: string, payload?: unknown): Promise<unknown> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 20000);
  try {
    const response = await fetch(path, payload === undefined ? { cache: 'no-store', signal: controller.signal } : {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: controller.signal,
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Maintenance request failed');
    return result;
  } catch (error) {
    if (controller.signal.aborted) throw new Error('Maintenance request timed out. Check saved records before retrying; the operation may have completed.');
    throw error;
  } finally { clearTimeout(timer); }
}
