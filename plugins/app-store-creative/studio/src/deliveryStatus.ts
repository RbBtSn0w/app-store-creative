export type LocalDeliveryStatus = {
  local_status: string;
  package_verified?: boolean;
  recipe_verified?: boolean;
  provenance_verified?: boolean;
};

export function deliveryVerdict(status: LocalDeliveryStatus): string {
  if (status.local_status === 'FAIL') return 'Local archive failed';
  if (status.local_status === 'PASS' && status.package_verified === true &&
      status.recipe_verified === true && status.provenance_verified === true) return 'Local archive verified';
  return 'Local verification incomplete';
}
