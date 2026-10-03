export type Region = Pick<DOMRect, 'left' | 'top' | 'right' | 'bottom'>;

export function layoutIssues(bounds: Region, texts: Region[], copy?: Region, device?: Region): string[] {
  const findings: string[] = [];
  if (texts.some(text => text.left < bounds.left - 1 || text.right > bounds.right + 1 ||
    text.top < bounds.top - 1 || text.bottom > bounds.bottom + 1)) {
    findings.push('Text is clipped; shorten the copy or select another layout');
  }
  if (copy && device && copy.left < device.right - 1 && copy.right > device.left + 1 &&
    copy.top < device.bottom - 1 && copy.bottom > device.top + 1) {
    findings.push('Copy overlaps the device; shorten the copy or select another layout');
  }
  return findings;
}

export function reviewCard(element: Element): string[] {
  const texts = Array.from(element.querySelectorAll('h2, p'));
  const findings = layoutIssues(element.getBoundingClientRect(), texts.map(text => text.getBoundingClientRect()),
    element.querySelector('[data-copy-region]')?.getBoundingClientRect(),
    element.querySelector('[data-device-frame]')?.getBoundingClientRect());
  if (!element.querySelector('h2')?.textContent?.trim()) findings.push('Enter a headline before exporting');
  if (texts.some(text => text.scrollWidth > text.clientWidth + 1)) {
    findings.push('Text exceeds its available width; shorten the copy');
  }
  return findings;
}
