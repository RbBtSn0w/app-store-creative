const nativeFamilies = new Set(['-apple-system', 'blinkmacsystemfont', 'system-ui', 'sans-serif', 'serif',
  'monospace', 'cursive', 'fantasy', 'ui-serif', 'ui-sans-serif', 'ui-monospace', 'ui-rounded']);

async function loadLocalFamily(family: string): Promise<void> {
  // FontFaceSet.check can return true for a nonexistent family using fallback.
  const face = new FontFace('CreativeRequiredFontProbe', `local(${JSON.stringify(family)})`);
  await face.load();
}

export async function requireConfiguredFont(stack?: string,
  load: (family: string) => Promise<void> = loadLocalFamily): Promise<void> {
  if (!stack?.trim()) return;
  const primary = stack.trim().match(/^("[^"]+"|'[^']+'|[^,]+)/)?.[1].trim();
  if (!primary) throw new Error('Enter a valid font family');
  const family = primary.replace(/^["']|["']$/g, '');
  if (nativeFamilies.has(family.toLowerCase())) return;
  try { await load(family); }
  catch { throw new Error(`Required font is unavailable: ${family}. Install it or choose a system font.`); }
}
