export async function readHistory<T>(path: string, label = 'production history'): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 20000);
  try {
    const response = await fetch(path, { signal: controller.signal });
    const body = await response.json();
    if (!response.ok) throw new Error(body.error || 'Could not load ' + label);
    return body;
  } catch (error) {
    if (controller.signal.aborted) {
      const subject = label === 'production history' ? 'History' : label.charAt(0).toUpperCase() + label.slice(1);
      throw new Error(subject + ' request timed out. Try again.');
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}
