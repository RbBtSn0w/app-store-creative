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
    storage = group('storage')
    storage.add_parser('inspect')
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
    seal = delivery.add_parser('seal')
    seal.add_argument('--candidate-id', required=True)
    seal.add_argument('--validation-id', required=True)
    seal.add_argument('--approval-id', required=True)
    seal.add_argument('--parent-revision')
    archive = group('archive')
    verify = archive.add_parser('verify')
    verify.add_argument('--path', type=Path, required=True)
    verify.add_argument('--expected-sha256')
    restore = archive.add_parser('restore')
    restore.add_argument('--path', type=Path, required=True)
    restore.add_argument('--destination', type=Path, required=True)
    restore.add_argument('--expected-sha256', required=True)
    publication = group('publication')
    plan = publication.add_parser('plan')
    plan.add_argument('--delivery-id', required=True)
    plan.add_argument('--archive-commit', required=True)
    plan.add_argument('--target', type=Path, required=True)
    publication_status = publication.add_parser('status')
    publication_status.add_argument('--id', required=True)
    publication_status.add_argument('--max-age-seconds', type=int, default=86400)
    observation = publication.add_parser('observe')
    observation.add_argument('--id', required=True)
    observation.add_argument('--observation', type=Path, required=True)
    export = publication.add_parser('export')
    export.add_argument('--id', required=True)
    export.add_argument('--confirm', action='store_true')
    upload_approval = approval.add_parser('record-upload')
    upload_approval.add_argument('--publication-id', required=True)
    upload_approval.add_argument('--actor', required=True)
    upload_approval.add_argument('--authorization-reference', required=True)
    upload_approval.add_argument('--confirm', choices=['APPROVE'], required=True)
    cleanup = group('cleanup')
    cleanup.add_parser('plan').add_argument('--retention-days', type=int, default=30)
    purge_plan = cleanup.add_parser('plan-purge')
    purge_plan.add_argument('--id', required=True)
    purge_plan.add_argument('--quarantine-days', type=int, default=7)
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
    imported.add_argument('--source', type=Path, required=True)
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
    if args.command == 'archive':
        from delivery_lifecycle import verify_archive, restore_archive
        if args.action == 'restore':
            return restore_archive(local(args.path), local(args.destination), args.expected_sha256)
        return verify_archive(local(args.path), args.expected_sha256)
    cfg = local(args.config or Path('creative.config.json'))
    if args.command == 'storage' and args.action in ('resume-relocate', 'rollback-relocate'):
        from relocation_lifecycle import recovery_source
        workspace = args.source_workspace if args.source_workspace.is_absolute() else root / args.source_workspace
        core = recovery_source(root, cfg, workspace, args.id)
        operation = core.resume_relocation if args.action == 'resume-relocate' else core.rollback_relocation
        return operation(args.id, args.actor, args.reason)
    core = Lifecycle(root, json.loads(cfg.read_text()), cfg)
    if args.command == 'storage':
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
            source = local(args.source)
            return core.import_capture(source.read_bytes(), args.name or source.name, args.actor)
        imported, path = core.resolve_import(args.path)
        return {**imported, 'local_path': str(path)}
    if args.command == 'inventory':
        return core.inventory()
    if args.command == 'run':
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
        if args.action == 'discard':
            return core.discard_candidate(args.id, args.actor, args.reason)
        if args.action == 'validate':
            return core.validate_candidate(args.id)
        return core.select(args.run_id, args.artifact)
    if args.command == 'publication':
        if args.action == 'observe':
            return core.record_observation(args.id, json.loads(local(args.observation).read_text()))
        if args.action == 'export':
            return core.export_publication(args.id, args.confirm)
        if args.action == 'plan':
            return core.plan_publication(args.delivery_id, args.archive_commit, json.loads(local(args.target).read_text()))
        return core.publication_status(args.id, args.max_age_seconds)
    if args.command == 'approval':
        if args.action == 'record-upload':
            return core.approve_upload(args.publication_id, args.actor, args.authorization_reference)
        return core.approve_design(args.candidate_id, args.validation_id, args.actor, args.authorization_reference)
    if args.command == 'delivery':
        return core.seal(args.candidate_id, args.validation_id, args.approval_id, args.parent_revision)
    raise ValueError('Unknown lifecycle command')
