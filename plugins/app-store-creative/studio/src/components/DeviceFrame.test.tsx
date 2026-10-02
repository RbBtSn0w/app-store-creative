import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { DeviceFrame } from './DeviceFrame';

// Captured Mac windows already contain their own native title bar and controls.
describe('Mac product-window framing', () => {
  it('presents the complete captured window without fabricated traffic lights', () => {
    const markup = renderToStaticMarkup(
      <DeviceFrame target="mac_16_10" screenshot="/real-window.png" />,
    );
    expect(markup).toContain('/real-window.png');
    expect(markup).not.toContain('#FF5F56');
    expect(markup).toContain('object-contain');
  });
});

it('preserves a native floating window without a wide artificial bezel', () => {
  const markup = renderToStaticMarkup(
    <DeviceFrame target="mac_16_10" screenshot="/quick-paste.png" nativeWindow maxWidth={320} maxHeight={360} />,
  );
  expect(markup).toContain('data-native-window="true"');
  expect(markup).toContain('max-width:320px');
  expect(markup).toContain('max-height:360px');
  expect(markup).not.toContain('bg-[#121214]');
  expect(markup).not.toContain('p-[8px]');
});
