import { expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { ArchivePolicySettings } from './ArchivePolicySettings';
it('leaves the archive choice undeclared during exploration', () => {
  const html = renderToStaticMarkup(<ArchivePolicySettings onChange={() => {}} />);
  expect(html).toContain('Not selected');
  expect(html).toContain('Choose before producing a release run');
  expect(html).not.toContain('Backend name');
});
it('exposes the portable backend name for an external declaration', () => {
  const html = renderToStaticMarkup(<ArchivePolicySettings policy={{ schema_version: 1, mediaMode: 'external', backend: 'team-media' }} onChange={() => {}} />);
  expect(html).toContain('Backend name');
  expect(html).toContain('team-media');
  expect(html).not.toContain('Backend path');
});
it('shows an explicit media budget without inventing one for exploration', () => {
  const html = renderToStaticMarkup(<ArchivePolicySettings onChange={() => {}} />);
  expect(html).toContain('Media budget (bytes)');
  expect(html).toContain('Leave empty for exploration');
});

it('preserves budget on invalid input but accepts intentional clearing and valid integers', () => {
  const change = vi.fn();
  const tree = ArchivePolicySettings({ onChange: () => {}, onBudgetChange: change, budget: 500 });
  const label = tree.props.children.find((child: any) => child?.type === 'label' && Array.isArray(child.props.children) && child.props.children[0] === 'Media budget (bytes)');
  const handler = label.props.children[1].props.onChange;
  for (const target of [
    { value: '', valueAsNumber: NaN, validity: { badInput: true } },
    { value: '-', valueAsNumber: NaN, validity: { badInput: false } },
    { value: '-1', valueAsNumber: -1, validity: { badInput: false } },
    { value: '1.5', valueAsNumber: 1.5, validity: { badInput: false } },
    { value: 'unsafe', valueAsNumber: Number.MAX_SAFE_INTEGER + 1, validity: { badInput: false } },
  ]) handler({ target });
  expect(change).not.toHaveBeenCalled();
  handler({ target: { value: '', valueAsNumber: NaN, validity: { badInput: false } } });
  expect(change).toHaveBeenLastCalledWith(undefined);
  handler({ target: { value: '1000', valueAsNumber: 1000, validity: { badInput: false } } });
  expect(change).toHaveBeenLastCalledWith(1000);
});
