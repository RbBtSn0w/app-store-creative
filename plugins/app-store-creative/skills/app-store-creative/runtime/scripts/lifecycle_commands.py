"""CLI use cases for the shared artifact lifecycle core."""
import argparse
import json
from pathlib import Path
from artifact_lifecycle import Lifecycle


def add_commands(subparsers):
    groups = []
    def group(name):
        parser = subparsers.add_parser(name)
        parser.add_argument('--repo', type=Path, default=Path.cwd())
        parser.add_argument('--config', type=Path)
        actions = parser.add_subparsers(dest='action', required=True)
        groups.append(actions)
        return actions
    history = group('history')
    history.add_parser('verify')
    history.add_parser('operations')
    inspection = history.add_parser('inspect-maintenance')
    inspection.add_argument('--id', required=True)
    abandon = history.add_parser('abandon')
    abandon.add_argument('--event-id', required=True)
    abandon.add_argument('--actor', required=True)
    abandon.add_argument('--reason', required=True)
    abandon.add_argument('--confirm', choices=['ABANDON'], required=True)
    preview = group('preview')
    recording = preview.add_parser('record')
    recording.add_argument('--run-id', required=True)
    recording.add_argument('--bundle-id', required=True)
    recording.add_argument('--window-id', type=int, required=True)
    recording.add_argument('--duration', type=float, default=30)
    recording.add_argument('--width', type=int, default=1920)
    recording.add_argument('--height', type=int, default=1080)
    recording.add_argument('--fps', type=int, default=30)
    recording.add_argument('--logical-path', required=True)
    recording.add_argument('--owner', required=True)
    recording.add_argument('--confirm', choices=['RECORD'], required=True)
    produce = preview.add_parser('produce')
    produce.add_argument('--run-id', required=True)
    produce.add_argument('--contract', type=Path, required=True)
    produce.add_argument('--logical-path', required=True)
    produce.add_argument('--owner', required=True)
    produce.add_argument('--confirm', choices=['EXECUTE'], required=True)
    poster = preview.add_parser('poster')
    poster.add_argument('--run-id', required=True)
    poster.add_argument('--preview-id', required=True)
    poster.add_argument('--timestamp', type=float, required=True)
    poster.add_argument('--owner', required=True)
    poster.add_argument('--retry-of')
    poster.add_argument('--confirm', choices=['EXTRACT'], required=True)
    storage = group('storage')
    reverse_switch = storage.add_parser('switch-reverse-relocate')
    reverse_switch.add_argument('--id', required=True)
    reverse_switch.add_argument('--actor', required=True)
    reverse_switch.add_argument('--reason', required=True)
    reverse_switch.add_argument('--confirm', choices=['SWITCH'], required=True)
    for name, confirmation in [('resume-reverse-relocate', 'RESUME'), ('rollback-reverse-relocate', 'ROLLBACK')]:
        reverse_recovery = storage.add_parser(name)
        reverse_recovery.add_argument('--id', required=True)
        reverse_recovery.add_argument('--source-workspace', type=Path, required=True)
        reverse_recovery.add_argument('--actor', required=True)
        reverse_recovery.add_argument('--reason', required=True)
        reverse_recovery.add_argument('--confirm', choices=[confirmation], required=True)
    reverse_prepare = storage.add_parser('prepare-reverse-relocate')
    reverse_prepare.add_argument('--id', required=True)
    reverse_prepare.add_argument('--actor', required=True)
    reverse_prepare.add_argument('--reason', required=True)
    reverse_prepare.add_argument('--confirm', choices=['PREPARE'], required=True)
    storage.add_parser('plan-reverse-relocate').add_argument('--id', required=True)
    storage.add_parser('verify-reverse-relocate').add_argument('--id', required=True)
    storage.add_parser('status-relocate').add_argument('--id', required=True)
    storage.add_parser('inspect-relocated-objects').add_argument('--id', required=True)
    storage.add_parser('inspect')
    storage.add_parser('artifact-policy')
    storage.add_parser('media-budget').add_argument('--candidate-id')
    storage.add_parser('preview').add_argument('--draft', type=Path, required=True)
    storage.add_parser('plan-relocate').add_argument('--storage', type=Path, required=True)
    storage.add_parser('verify-relocate').add_argument('--id', required=True)
    storage.add_parser('relocation-git-policy').add_argument('--id', required=True)
    prepare = storage.add_parser('prepare-relocate')
    prepare.add_argument('--id', required=True)
    prepare.add_argument('--actor', required=True)
    prepare.add_argument('--reason', required=True)
    prepare.add_argument('--confirm', choices=['PREPARE'], required=True)
    for action, confirmation in [('recover-relocate', 'RECOVER'), ('cancel-relocate', 'CANCEL'), ('switch-relocate', 'SWITCH')]:
        operation = storage.add_parser(action)
        operation.add_argument('--id', required=True)
        operation.add_argument('--actor', required=True)
        operation.add_argument('--reason', required=True)
        operation.add_argument('--confirm', choices=[confirmation], required=True)
    for action in ['resume', 'rollback']:
        operation = storage.add_parser(action + '-relocate')
        operation.add_argument('--id', required=True)
        operation.add_argument('--source-workspace', type=Path, required=True)
        operation.add_argument('--actor', required=True)
        operation.add_argument('--reason', required=True)
        operation.add_argument('--confirm', choices=[action.upper()], required=True)
    storage.add_parser('git-policy').add_argument('--media-mode', choices=['git', 'lfs', 'external'], default='git')
    run = group('run')
    run.add_parser('start').add_argument('--target', type=Path, required=True)
    run.add_parser('status').add_argument('--id', required=True)
    listing = run.add_parser('list')
    listing.add_argument('--limit', type=int, default=20)
    listing.add_argument('--cursor')
    attempt = group('attempt')
    start = attempt.add_parser('start')
    start.add_argument('--run-id', required=True)
    start.add_argument('--stage', required=True)
    start.add_argument('--owner', required=True)
    start.add_argument('--retry-of')
    start.add_argument('--lease-seconds', type=int, default=3600)
    finish = attempt.add_parser('finish')
    finish.add_argument('--id', required=True)
    finish.add_argument('--status', required=True, choices=['succeeded', 'failed', 'cancelled', 'interrupted'])
    finish.add_argument('--reason')
    finish.add_argument('--lease-token', required=True)
    renew = attempt.add_parser('renew')
    renew.add_argument('--id', required=True)
    renew.add_argument('--lease-token', required=True)
    renew.add_argument('--lease-seconds', type=int, default=3600)
    recover = attempt.add_parser('recover')
    recover.add_argument('--id', required=True)
    recover.add_argument('--owner', required=True)
    recover.add_argument('--reason', required=True)
    recover.add_argument('--lease-seconds', type=int, default=3600)
    recover.add_argument('--confirm', choices=['RECOVER'], required=True)
    artifact = group('artifact')
    register = artifact.add_parser('register')
    register.add_argument('--attempt-id', required=True)
    register.add_argument('--source', type=Path, required=True)
    register.add_argument('--role', required=True)
    register.add_argument('--media-type')
    register.add_argument('--partial', action='store_true')
    register.add_argument('--input', action='append', default=[])
    register.add_argument('--logical-path')
    register.add_argument('--lease-token', required=True)
    artifact.add_parser('verify').add_argument('--id', required=True)
    candidate = group('candidate')
    select = candidate.add_parser('select')
    select.add_argument('--run-id', required=True)
    select.add_argument('--artifact', action='append', required=True)
    candidate.add_parser('validate').add_argument('--id', required=True)
    candidate.add_parser('review').add_argument('--id', required=True)
    discard = candidate.add_parser('discard')
    discard.add_argument('--id', required=True)
    discard.add_argument('--actor', required=True)
    discard.add_argument('--reason', required=True)
    discard.add_argument('--confirm', choices=['DISCARD'], required=True)
    approval = group('approval')
    record = approval.add_parser('record')
    record.add_argument('--candidate-id', required=True)
    record.add_argument('--validation-id', required=True)
    record.add_argument('--actor', required=True)
    record.add_argument('--authorization-reference', required=True)
    record.add_argument('--confirm', choices=['APPROVE'], required=True)
    delivery = group('delivery')
    delivery.add_parser('status').add_argument('--id', required=True)
    listing = delivery.add_parser('list')
    listing.add_argument('--limit', type=int, default=20)
    listing.add_argument('--cursor')
    seal = delivery.add_parser('seal')
    seal.add_argument('--candidate-id', required=True)
    seal.add_argument('--validation-id', required=True)
    seal.add_argument('--approval-id', required=True)
    seal.add_argument('--parent-revision')
    archive = group('archive')
    retrieve_evidence = archive.add_parser('retrieve-evidence')
    retrieve_evidence.add_argument('--path', type=Path, required=True)
    retrieve_evidence.add_argument('--expected-sha256', required=True)
    retrieve_evidence.add_argument('--backend-root', type=Path, required=True)
    retrieve_evidence.add_argument('--destination', type=Path, required=True)
    for name, field in [('persist-media', 'artifact-id'), ('restore-media', 'reference-id')]:
        operation = archive.add_parser(name)
        operation.add_argument('--' + field, required=True)
        operation.add_argument('--backend', required=True)
        operation.add_argument('--backend-root', type=Path)
        operation.add_argument('--confirm', choices=['PERSIST' if name == 'persist-media' else 'RESTORE'], required=True)
    externalize = archive.add_parser('externalize')
    externalize.add_argument('--delivery-id', required=True)
    externalize.add_argument('--backend', required=True)
    externalize.add_argument('--backend-root', type=Path)
    externalize.add_argument('--confirm', choices=['EXTERNALIZE'], required=True)
    external_restore = archive.add_parser('restore-external')
    external_restore.add_argument('--path', type=Path, required=True)
    external_restore.add_argument('--destination', type=Path, required=True)
    external_restore.add_argument('--expected-sha256', required=True)
    external_restore.add_argument('--backend', required=True)
    external_restore.add_argument('--backend-root', type=Path, required=True)
    external_restore.add_argument('--confirm', choices=['RESTORE'], required=True)
    external_git = archive.add_parser('verify-external-git')
    external_git.add_argument('--commit', required=True)
    external_git.add_argument('--path', required=True)
    external_git.add_argument('--expected-sha256', required=True)
    external_git.add_argument('--backend', required=True)
    external_git.add_argument('--backend-root', type=Path, required=True)
    external_git.add_argument('--remote')
    retrieve = archive.add_parser('verify-git')
    retrieve.add_argument('--commit', required=True)
    retrieve.add_argument('--remote')
    retrieve.add_argument('--path', required=True)
    retrieve.add_argument('--expected-sha256', required=True)
    verify = archive.add_parser('verify')
    verify.add_argument('--path', type=Path, required=True)
    verify.add_argument('--expected-sha256')
    restore = archive.add_parser('restore')
    restore.add_argument('--path', type=Path, required=True)
    restore.add_argument('--destination', type=Path, required=True)
    restore.add_argument('--expected-sha256', required=True)
    publication = group('publication')
    listing = publication.add_parser('list')
    listing.add_argument('--limit', type=int, default=20)
    listing.add_argument('--cursor')
    plan = publication.add_parser('plan')
    plan.add_argument('--delivery-id', required=True)
    plan.add_argument('--archive-commit', required=True)
    plan.add_argument('--archive-remote')
    plan.add_argument('--target', type=Path, required=True)
    external_plan = publication.add_parser('plan-external')
    external_plan.add_argument('--external-archive-id', required=True)
    external_plan.add_argument('--archive-commit', required=True)
    external_plan.add_argument('--archive-path', required=True)
    external_plan.add_argument('--archive-remote')
    external_plan.add_argument('--backend-root', type=Path)
    external_plan.add_argument('--target', type=Path, required=True)
    prepare_external = publication.add_parser('prepare-external')
    prepare_external.add_argument('--id', required=True)
    prepare_external.add_argument('--backend-root', type=Path)
    prepare_external.add_argument('--destination', type=Path, required=True)
    prepare_external.add_argument('--confirm', choices=['PREPARE'], required=True)
    preparation_status = publication.add_parser('preparation-status')
    preparation_status.add_argument('--id', required=True)
    publication_status = publication.add_parser('status')
    publication_status.add_argument('--id', required=True)
    publication_status.add_argument('--max-age-seconds', type=int, default=86400)
    observation = publication.add_parser('observe')
    observation.add_argument('--id', required=True)
    observation.add_argument('--observation', type=Path, required=True)
    observation.add_argument('--evidence', type=Path, required=True)
    retain = publication.add_parser('retain-evidence')
    retain.add_argument('--observation-id', required=True)
    retain.add_argument('--evidence', type=Path, required=True)
    retain.add_argument('--actor', required=True)
    persist_evidence = publication.add_parser('persist-evidence')
    persist_evidence.add_argument('--evidence-id', required=True)
    persist_evidence.add_argument('--backend', required=True)
    persist_evidence.add_argument('--backend-root', type=Path)
    normalize = publication.add_parser('normalize-asc-preview')
    normalize.add_argument('--id', required=True)
    normalize.add_argument('--response', type=Path, required=True)
    normalize.add_argument('--scope', type=Path, required=True)
    export = publication.add_parser('export')
    export.add_argument('--id', required=True)
    export.add_argument('--confirm', action='store_true')
    upload_approval = approval.add_parser('record-upload')
    upload_approval.add_argument('--publication-id', required=True)
    upload_approval.add_argument('--actor', required=True)
    upload_approval.add_argument('--authorization-reference', required=True)
    upload_approval.add_argument('--confirm', choices=['APPROVE'], required=True)
    cleanup = group('cleanup')
    cleanup.add_parser('plan').add_argument('--retention-days', type=int)
    cleanup.add_parser('plan-relocation-retention').add_argument('--retention-days', type=int)
    cleanup.add_parser('verify-relocation-retention').add_argument('--id', required=True)
    relocation_purge = cleanup.add_parser('plan-relocation-purge')
    relocation_purge.add_argument('--id', required=True)
    relocation_purge.add_argument('--quarantine-days', type=int)
    cleanup.add_parser('verify-relocation-purge').add_argument('--id', required=True)
    cancellation = cleanup.add_parser('cancel-relocation-quarantine-preparation')
    cancellation.add_argument('--id', required=True)
    cancellation.add_argument('--actor', required=True)
    cancellation.add_argument('--reason', required=True)
    cancellation.add_argument('--confirm', choices=['CANCEL'], required=True)
    relocation_delete = cleanup.add_parser('purge-relocation')
    relocation_delete.add_argument('--id', required=True)
    relocation_delete.add_argument('--actor', required=True)
    relocation_delete.add_argument('--reason', required=True)
    relocation_delete.add_argument('--confirm', choices=['PURGE'], required=True)
    for name, confirmation in [('commit-relocation-quarantine', 'QUARANTINE'), ('restore-relocation-quarantine', 'RESTORE')]:
        operation = cleanup.add_parser(name)
        operation.add_argument('--id', required=True)
        operation.add_argument('--actor', required=True)
        operation.add_argument('--reason', required=True)
        operation.add_argument('--confirm', choices=[confirmation], required=True)
    for name in ['prepare-relocation-quarantine', 'resume-relocation-quarantine-preparation']:
        preparation = cleanup.add_parser(name)
        preparation.add_argument('--id', required=True)
        preparation.add_argument('--actor', required=True)
        preparation.add_argument('--reason', required=True)
        preparation.add_argument('--confirm', choices=['PREPARE'], required=True)
    purge_plan = cleanup.add_parser('plan-purge')
    purge_plan.add_argument('--id', required=True)
    purge_plan.add_argument('--quarantine-days', type=int)
    for name, confirmation in [('quarantine', 'QUARANTINE'), ('restore', 'RESTORE'), ('purge', 'PURGE')]:
        operation = cleanup.add_parser(name)
        operation.add_argument('--id', required=True)
        operation.add_argument('--actor', required=True)
        operation.add_argument('--reason', required=True)
        operation.add_argument('--confirm', choices=[confirmation], required=True)
    incident = group('incident')
    opened = incident.add_parser('open')
    opened.add_argument('--actor', required=True)
    opened.add_argument('--reason', required=True)
    opened.add_argument('--artifact', action='append', default=[])
    opened.add_argument('--candidate', action='append', default=[])
    opened.add_argument('--delivery', action='append', default=[])
    closed = incident.add_parser('close')
    closed.add_argument('--id', required=True)
    closed.add_argument('--actor', required=True)
    closed.add_argument('--resolution', required=True)
    closed.add_argument('--confirm', choices=['CLOSE'], required=True)
    incident.add_parser('status').add_argument('--id', required=True)
    source_input = group('input')
    imported = source_input.add_parser('import')
    capture_origin = imported.add_mutually_exclusive_group(required=True)
    capture_origin.add_argument('--source', type=Path)
    capture_origin.add_argument('--artifact', help='Existing complete capture artifact ID')
    imported.add_argument('--name')
    imported.add_argument('--actor', required=True)
    source_input.add_parser('resolve').add_argument('--path', required=True)
    source_input.add_parser('status').add_argument('--id', required=True)
    input_discard = source_input.add_parser('discard')
    input_discard.add_argument('--id', required=True)
    input_discard.add_argument('--actor', required=True)
    input_discard.add_argument('--reason', required=True)
    input_discard.add_argument('--confirm', choices=['DISCARD'], required=True)
    inventory = subparsers.add_parser('inventory')
    inventory.add_argument('--repo', type=Path, default=Path.cwd())
    inventory.add_argument('--config', type=Path)
    for actions in groups:
        for action in actions.choices.values():
            action.add_argument('--repo', type=Path, default=argparse.SUPPRESS)
            action.add_argument('--config', type=Path, default=argparse.SUPPRESS)


def execute(args):
    root = args.repo.resolve()
    def local(path):
        return path.resolve() if path.is_absolute() else (root / path).resolve()
    if args.command == 'archive' and args.action == 'retrieve-evidence':
        from remote_observations import retrieve_observation_evidence
        return retrieve_observation_evidence(local(args.path), args.expected_sha256,
            local(args.backend_root), local(args.destination))
    if args.command == 'archive' and args.action == 'verify-external-git':
        from external_delivery_archive import verify_external_git
        return verify_external_git(root, args.commit, args.path, args.expected_sha256,
                                   args.backend, args.backend_root, args.remote)
    if args.command == 'archive' and args.action == 'restore-external':
        from external_delivery_archive import restore_external
        return restore_external(local(args.path), local(args.destination), args.backend,
                                args.backend_root, args.expected_sha256)
    if args.command == 'archive' and args.action == 'externalize':
        core = Lifecycle.from_configuration(root, local(args.config or Path('creative.config.json')))
        return core.export_external_delivery(args.delivery_id, args.backend, args.backend_root)
    if args.command == 'archive' and args.action in ('persist-media', 'restore-media'):
        core = Lifecycle.from_configuration(root, local(args.config or Path('creative.config.json')))
        operation = core.persist_external_media if args.action == 'persist-media' else core.restore_external_media
        identity = args.artifact_id if args.action == 'persist-media' else args.reference_id
        return operation(identity, args.backend, args.backend_root)
    if args.command == 'archive':
        from delivery_lifecycle import verify_archive, restore_archive, verify_git_archive
        if args.action == 'verify-git':
            return verify_git_archive(root, args.commit, args.path, args.expected_sha256, args.remote)
        if args.action == 'restore':
            return restore_archive(local(args.path), local(args.destination), args.expected_sha256)
        return verify_archive(local(args.path), args.expected_sha256)
    cfg = local(args.config or Path('creative.config.json'))
    if args.command == 'storage' and args.action in ('resume-relocate', 'rollback-relocate', 'resume-reverse-relocate', 'rollback-reverse-relocate'):
        from relocation_lifecycle import recovery_source
        workspace = args.source_workspace if args.source_workspace.is_absolute() else root / args.source_workspace
        core = recovery_source(root, cfg, workspace, args.id)
        operation = (core.rollback_reverse_relocation if args.action == 'rollback-reverse-relocate' else
                     core.resume_reverse_relocation if args.action == 'resume-reverse-relocate' else
                     core.resume_relocation if args.action == 'resume-relocate' else core.rollback_relocation)
        return operation(args.id, args.actor, args.reason)
    if args.command == 'storage' and args.action == 'preview':
        from storage_configuration import preview_configuration
        return preview_configuration(root, json.loads(local(args.draft).read_text()), cfg)
    core = Lifecycle.from_configuration(root, cfg)
    if args.command == 'history':
        if args.action == 'inspect-maintenance':
            return core.maintenance_status(args.id)
        if args.action == 'abandon':
            return core.abandon_commit(args.event_id, args.actor, args.reason)
        return core.operation_journals() if args.action == 'operations' else core.verify_history()
    if args.command == 'preview':
        if args.action == 'record':
            from managed_recording import record
            return record(core, args.run_id, args.bundle_id, args.window_id, args.duration,
                          args.width, args.height, args.fps, args.logical_path, args.owner)
        if args.action == 'poster':
            from managed_poster import produce
            return produce(core, args.run_id, args.preview_id, args.timestamp, args.owner, retry_of=args.retry_of)
        from managed_preview import produce
        return produce(core, args.run_id, local(args.contract), args.logical_path, args.owner)
    if args.command == 'storage':
        if args.action == 'switch-reverse-relocate':
            return core.switch_reverse_relocation(args.id, args.actor, args.reason)
        if args.action == 'prepare-reverse-relocate':
            return core.prepare_reverse_relocation(args.id, args.actor, args.reason)
        if args.action == 'plan-reverse-relocate':
            return core.plan_reverse_relocation(args.id)
        if args.action == 'verify-reverse-relocate':
            return core.verify_reverse_relocation_plan(args.id)
        if args.action == 'media-budget':
            return core.media_budget(args.candidate_id)
        if args.action == 'artifact-policy':
            return core.inspect_artifact_policy()
        if args.action == 'inspect-relocated-objects':
            return core.relocated_object_status(args.id)
        if args.action == 'status-relocate':
            return core.relocation_status(args.id)
        if args.action == 'inspect':
            return core.paths.binding()
        if args.action == 'plan-relocate':
            return core.plan_relocation(json.loads(local(args.storage).read_text()))
        if args.action == 'relocation-git-policy':
            return core.relocation_git_policy(args.id)
        if args.action == 'switch-relocate':
            return core.switch_relocation(args.id, args.actor, args.reason)
        if args.action == 'prepare-relocate':
            return core.prepare_relocation(args.id, args.actor, args.reason)
        if args.action == 'recover-relocate':
            return core.recover_relocation(args.id, args.actor, args.reason)
        if args.action == 'cancel-relocate':
            return core.cancel_relocation(args.id, args.actor, args.reason)
        if args.action == 'verify-relocate':
            return core.verify_relocation_plan(args.id)
        return core.git_policy(args.media_mode)
    if args.command == 'cleanup':
        if args.action == 'cancel-relocation-quarantine-preparation':
            return core.cancel_relocation_quarantine_preparation(args.id, args.actor, args.reason)
        if args.action == 'purge-relocation':
            return core.purge_relocation(args.id, args.actor, args.reason)
        if args.action == 'plan-relocation-purge':
            return core.plan_relocation_purge(args.id, args.quarantine_days)
        if args.action == 'verify-relocation-purge':
            return core.verify_relocation_purge(args.id)
        if args.action == 'commit-relocation-quarantine':
            return core.commit_relocation_quarantine(args.id, args.actor, args.reason)
        if args.action == 'restore-relocation-quarantine':
            return core.restore_relocation_quarantine(args.id, args.actor, args.reason)
        if args.action == 'prepare-relocation-quarantine':
            return core.prepare_relocation_quarantine(args.id, args.actor, args.reason)
        if args.action == 'resume-relocation-quarantine-preparation':
            return core.resume_relocation_quarantine_preparation(args.id, args.actor, args.reason)
        if args.action == 'verify-relocation-retention':
            return core.verify_relocation_retention(args.id)
        if args.action == 'plan-relocation-retention':
            return core.plan_relocation_retention(retention_days=args.retention_days)
        if args.action == 'plan':
            return core.plan_cleanup(args.retention_days)
        if args.action == 'plan-purge':
            return core.plan_purge(args.id, args.quarantine_days)
        if args.action == 'purge':
            return core.purge_cleanup(args.id, args.actor, args.reason)
        if args.action == 'quarantine':
            return core.quarantine_cleanup(args.id, args.actor, args.reason)
        return core.restore_cleanup(args.id, args.actor, args.reason)
    if args.command == 'incident':
        if args.action == 'open':
            return core.open_incident(args.actor, args.reason, args.artifact, args.candidate, args.delivery)
        if args.action == 'close':
            return core.close_incident(args.id, args.actor, args.resolution)
        return core.incident_status(args.id)
    if args.command == 'input':
        if args.action == 'discard':
            return core.discard_input(args.id, args.actor, args.reason)
        if args.action == 'status':
            return core.input_status(args.id)
        if args.action == 'import':
            if args.artifact:
                return core.import_capture_artifact(args.artifact, args.actor, args.name)
            source = local(args.source)
            return core.import_capture(source.read_bytes(), args.name or source.name, args.actor)
        imported, path = core.resolve_import(args.path)
        return {**imported, 'local_path': str(path)}
    if args.command == 'inventory':
        return core.inventory()
    if args.command == 'run':
        if args.action == 'list':
            return core.list_runs(args.limit, args.cursor)
        if args.action == 'start':
            return core.start_run(json.loads(local(args.target).read_text()))
        return core.status(args.id)
    if args.command == 'attempt':
        if args.action == 'start':
            return core.start_attempt(args.run_id, args.stage, args.owner, args.retry_of, args.lease_seconds)
        if args.action == 'renew':
            return core.renew_attempt(args.id, args.lease_token, args.lease_seconds)
        if args.action == 'recover':
            return core.recover_attempt(args.id, args.owner, args.reason, args.lease_seconds)
        return core.finish_attempt(args.id, args.status, args.reason, args.lease_token)
    if args.command == 'artifact':
        if args.action == 'register':
            return core.register(args.attempt_id, local(args.source), args.role,
                                 args.media_type, args.partial, args.input, args.logical_path, args.lease_token)
        return core.verify_artifact(args.id)
    if args.command == 'candidate':
        if args.action == 'review':
            return core.candidate_review(args.id)
        if args.action == 'discard':
            return core.discard_candidate(args.id, args.actor, args.reason)
        if args.action == 'validate':
            return core.validate_candidate(args.id)
        return core.select(args.run_id, args.artifact)
    if args.command == 'publication':
        if args.action == 'list':
            return core.list_publications(args.limit, args.cursor)
        if args.action == 'normalize-asc-preview':
            from asc_observation_adapter import preview_observations
            from configuration_layers import _read_regular
            response = _read_regular(local(args.response))
            scope = json.loads(_read_regular(local(args.scope)))
            with core.transaction():
                plan = core._read('publications', args.id, 'plan')
                return {'remote_write': False, 'observations': preview_observations(plan, response, scope)}
        if args.action == 'persist-evidence':
            return core.persist_observation_evidence(args.evidence_id, args.backend,
                local(args.backend_root) if args.backend_root else None)
        if args.action == 'retain-evidence':
            from configuration_layers import _read_regular
            return core.retain_observation_evidence(args.observation_id, _read_regular(local(args.evidence)), args.actor)
        if args.action == 'observe':
            from configuration_layers import _read_regular
            observation = json.loads(_read_regular(local(args.observation)))
            evidence = _read_regular(local(args.evidence))
            return core.record_observation(args.id, observation, evidence)
        if args.action == 'export':
            return core.export_publication(args.id, args.confirm)
        if args.action == 'preparation-status':
            return core.external_preparation_status(args.id)
        if args.action == 'prepare-external':
            return core.prepare_external_publication(args.id, local(args.backend_root) if args.backend_root else None, local(args.destination))
        if args.action == 'plan-external':
            return core.plan_external_publication(args.external_archive_id, args.archive_commit,
                args.archive_path, json.loads(local(args.target).read_text()), local(args.backend_root) if args.backend_root else None, args.archive_remote)
        if args.action == 'plan':
            return core.plan_publication(args.delivery_id, args.archive_commit, json.loads(local(args.target).read_text()), args.archive_remote)
        return core.publication_status(args.id, args.max_age_seconds)
    if args.command == 'approval':
        if args.action == 'record-upload':
            return core.approve_upload(args.publication_id, args.actor, args.authorization_reference)
        return core.approve_design(args.candidate_id, args.validation_id, args.actor, args.authorization_reference)
    if args.command == 'delivery':
        if args.action == 'list':
            return core.list_deliveries(args.limit, args.cursor)
        if args.action == 'status':
            return core.delivery_status(args.id)
        return core.seal(args.candidate_id, args.validation_id, args.approval_id, args.parent_revision)
    raise ValueError('Unknown lifecycle command')
