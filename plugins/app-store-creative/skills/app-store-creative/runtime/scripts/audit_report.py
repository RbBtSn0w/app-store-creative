"""Markdown provenance audit report composed from public lifecycle query surfaces."""

from datetime import datetime, timezone


def _all_pages(fetch, key, limit=100):
    items = []
    cursor = None
    while True:
        page = fetch(limit=limit, cursor=cursor)
        items.extend(page[key])
        cursor = page.get('next_cursor')
        if not cursor:
            break
    return items


def _abbrev(sha256, length=12):
    return sha256[:length] if isinstance(sha256, str) and len(sha256) >= length else str(sha256)


def _collect_gaps(state):
    gaps = []
    for artifact in state['artifacts']:
        if artifact.get('partial'):
            gaps.append(('partial-artifact', artifact['id'], 'Artifact is partial'))
        if artifact.get('object_integrity') != 'PASS':
            gaps.append(('integrity', artifact['id'],
                         f"Integrity is {artifact.get('object_integrity', 'unverified')}"))
        if not artifact.get('candidate_eligible', True):
            for error in artifact.get('eligibility_errors', []):
                gaps.append(('eligibility', artifact['id'], error))
    for candidate in state['candidates']:
        if not candidate.get('design_approvals'):
            gaps.append(('approval', candidate['id'], 'No design approval recorded'))
        for approval in candidate.get('design_approvals', []):
            if approval.get('binding_status') != 'PASS':
                reasons = '; '.join(approval.get('binding_errors', [])) or 'binding check failed'
                gaps.append(('approval-binding', approval['id'],
                             f"Binding {approval['binding_status']}: {reasons}"))
        disposition = candidate.get('disposition')
        if disposition:
            gaps.append(('disposition', candidate['id'],
                         f"Candidate disposition: {disposition.get('reason', 'unspecified')}"))
    return gaps


def generate_report(core, run_id):
    """Generate a Markdown provenance audit report for a lifecycle run."""
    generated = datetime.now(timezone.utc).isoformat()
    state = core.status(run_id)
    deliveries = _all_pages(core.list_deliveries, 'deliveries')
    publications = _all_pages(core.list_publications, 'publications')

    artifacts = state['artifacts']
    candidates = state['candidates']
    attempts = state['attempts']
    attempt_map = {a['id']: a for a in attempts}
    receipts = [a for a in artifacts if a['role'] == 'producer-evidence']
    gaps = _collect_gaps(state)
    if not receipts:
        gaps.insert(0, ('receipt', run_id, 'No producer-evidence receipt in this run'))

    lines = []
    lines.append('# Provenance Audit Report')
    lines.append('')
    lines.append(f'- **Run:** `{run_id}`')
    lines.append(f'- **Generated:** {generated}')
    integrity = (f'artifacts={len(artifacts)} receipts={len(receipts)} '
                 f'candidates={len(candidates)} '
                 f'approvals={sum(len(c.get("design_approvals", [])) for c in candidates)} '
                 f'gaps={len(gaps)}')
    lines.append(f'- **Integrity:** `{integrity}`')
    lines.append(f'- **Gaps:** {len(gaps)}')
    lines.append('')

    lines.append('## Gaps')
    lines.append('')
    if gaps:
        lines.append('| # | Type | ID | Detail |')
        lines.append('|---|------|----|--------|')
        for i, (kind, identity, detail) in enumerate(gaps, 1):
            lines.append(f'| {i} | {kind} | `{identity}` | {detail} |')
    else:
        lines.append('No gaps detected.')
    lines.append('')

    lines.append('## Artifact Inventory')
    lines.append('')
    for artifact in artifacts:
        is_receipt = artifact['role'] == 'producer-evidence'
        label = ' (receipt)' if is_receipt else ''
        lines.append(f"### `{artifact['id']}`{label}")
        lines.append('')
        lines.append(f"- **Role:** {artifact['role']}")
        if artifact.get('logical_path'):
            lines.append(f"- **Path:** `{artifact['logical_path']}`")
        lines.append(f"- **SHA-256:** `{_abbrev(artifact['sha256'])}`")
        lines.append(f"- **Size:** {artifact.get('size_bytes', '?')} bytes")
        lines.append(f"- **Partial:** {'Yes' if artifact.get('partial') else 'No'}")
        lines.append(f"- **Integrity:** {artifact.get('object_integrity', 'unverified')}")
        lines.append(f"- **Eligible:** {'Yes' if artifact.get('candidate_eligible') else 'No'}")
        attempt = attempt_map.get(artifact.get('attempt_id'))
        if attempt:
            outcome = attempt.get('outcome') or {}
            lines.append(f"- **Producer:** `{attempt['id']}` ({attempt.get('stage', '?')})"
                         f" — {outcome.get('status', 'no outcome recorded')}")
            if attempt.get('implementation'):
                lines.append(f"- **Implementation:** {attempt['implementation']}")
        inputs = artifact.get('inputs') or []
        if inputs:
            lines.append(f"- **Inputs:** {', '.join(f'`{i}`' for i in inputs)}")
        provenance = artifact.get('experiment_provenance')
        if provenance:
            lines.append(f"- **Experiment:** `{provenance.get('experiment_id', '?')}`"
                         f" variant `{provenance.get('variant_id', '?')}`")
        lines.append('')

    lines.append('## Receipts')
    lines.append('')
    if receipts:
        lines.append('| Artifact | Consumed by | Path |')
        lines.append('|----------|------------|------|')
        for receipt in receipts:
            consumers = [a['id'] for a in artifacts if receipt['id'] in (a.get('inputs') or [])]
            ref = ', '.join(f'`{c}`' for c in consumers) if consumers else '—'
            lines.append(f"| `{receipt['id']}` | {ref} | `{receipt.get('logical_path', '—')}` |")
    else:
        lines.append('No producer-evidence receipts in this run.')
    lines.append('')

    lines.append('## Approvals')
    lines.append('')
    has_approvals = False
    for candidate in candidates:
        for approval in candidate.get('design_approvals', []):
            has_approvals = True
            lines.append(f"- **Candidate** `{candidate['id']}` → **Approval** `{approval['id']}`")
            lines.append(f"  - Actor: {approval.get('actor', '—')}")
            lines.append(f"  - Authorization: {approval.get('authorization_reference', '—')}")
            lines.append(f"  - Binding: {approval.get('binding_status', '—')}")
    if not has_approvals:
        lines.append('No design approvals recorded.')
    lines.append('')

    lines.append('## Delivery References')
    lines.append('')
    if deliveries:
        lines.append('| Delivery | Created | Target | Parent | Status |')
        lines.append('|----------|---------|--------|--------|--------|')
        for d in deliveries:
            target = d.get('target') or {}
            target_str = f"{target.get('platform', '?')} {target.get('version', '?')}"
            parent = d.get('parent_revision') or '—'
            status = core.delivery_status(d['id'])
            lines.append(f"| `{d['id']}` | {d.get('created_at', '—')} | {target_str} | `{parent}` |"
                         f" {status.get('local_status', '—')} |")
    else:
        lines.append('No deliveries recorded.')
    lines.append('')

    lines.append('## Publication References')
    lines.append('')
    if publications:
        lines.append('| Publication | Delivery | Created |')
        lines.append('|-------------|----------|---------|')
        for p in publications:
            lines.append(f"| `{p['id']}` | `{p.get('delivery_id', '—')}` | {p.get('created_at', '—')} |")
    else:
        lines.append('No publications recorded.')
    lines.append('')

    return '\n'.join(lines)
