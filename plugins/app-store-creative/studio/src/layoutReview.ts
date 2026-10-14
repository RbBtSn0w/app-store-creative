export type Region = Pick<DOMRect, 'left' | 'top' | 'right' | 'bottom'>;

export function layoutIssues(bounds: Region, texts: Region[], copy?: Region, device?: Region): string[] {
  const findings: string[] = [];
  if (texts.some(text => text.left < bounds.left - 1 || text.right > bounds.right + 1 ||
    text.top < bounds.top - 1 || text.bottom > bounds.bottom + 1)) {
    findings.push('Text is clipped; shorten the copy or select another layout');
  }
  // Allow 4px tolerance to prevent false positives from 3D drop-shadows and projection bounds
  if (copy && device && copy.left < device.right - 4 && copy.right > device.left + 4 &&
    copy.top < device.bottom - 4 && copy.bottom > device.top + 4) {
    findings.push('Copy overlaps the device; shorten the copy or select another layout');
  }
  return findings;
}

export function reviewCard(element: Element): string[] {
  const texts = Array.from(element.querySelectorAll('h2, p'));
  const innerContent = element.querySelector('[data-native-window="true"] img, [data-device-frame] .overflow-hidden, [data-device-frame]');
  const findings = layoutIssues(element.getBoundingClientRect(), texts.map(text => text.getBoundingClientRect()),
    element.querySelector('[data-copy-region]')?.getBoundingClientRect(),
    innerContent?.getBoundingClientRect());
  if (!element.querySelector('h2')?.textContent?.trim()) findings.push('Enter a headline before exporting');
  if (texts.some(text => text.scrollWidth > text.clientWidth + 1)) {
    findings.push('Text exceeds its available width; shorten the copy');
  }
  return findings;
}
