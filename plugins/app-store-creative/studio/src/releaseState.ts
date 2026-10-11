interface ReleaseState {
  hasCards: boolean; dirty: boolean; saving: boolean; busy: boolean; exporting: boolean;
  verified: boolean; policyChecked?: boolean; error: boolean; inputsChecked: boolean; inputsMissing: boolean; layoutErrors: boolean;
}

export function releaseState(state: ReleaseState): string {
  if (state.busy) return state.exporting ? 'Exporting' : 'Working';
  if (state.saving) return 'Saving changes';
  if (state.dirty) return 'Unsaved changes';
  if (state.error || state.layoutErrors) return 'Needs attention';
  if (state.verified) return 'Verified locally';
  if (state.policyChecked) return 'Candidate checks passed';
  if (!state.hasCards || !state.inputsChecked || state.inputsMissing) return 'Needs input';
  return 'Ready to export';
}
