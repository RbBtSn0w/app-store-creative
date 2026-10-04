"""Managed source imports with stable HTTP aliases and provenance."""
from pathlib import Path
import re


IMPORT_PATH = re.compile(r'^api/inputs/([a-z0-9]+)/capture\.(png|jpg|jpeg)$')
SNAPSHOT_INDEX = '.creative-input-snapshot.json'


def imported_identity(name):
    match = IMPORT_PATH.fullmatch(name.lstrip('/')) if isinstance(name, str) else None
    return match.group(1) if match else None


def write_snapshot_index(root, sources):
    aliases = {name: sha for name, sha in sources.items() if imported_identity(name)}
    if aliases:
        from artifact_lifecycle import canonical
        (Path(root) / SNAPSHOT_INDEX).write_bytes(canonical(aliases))


class InputOperations:
    def import_capture(self, data, name, actor):
        import studio_contract
        if not isinstance(actor, str) or not actor.strip() or not isinstance(name, str) or not name.strip():
            raise ValueError('Import requires actor and source name')
        width, height, extension = studio_contract.inspect_capture(data)
        run = self.start_run({'stage': 'source-import'})
        attempt = self.start_attempt(run['id'], 'import', actor)
        logical = f"api/inputs/{attempt['id']}/capture.{extension}"
        try:
            source = self.work_path(attempt['id']) / ('capture.' + extension)
            source.write_bytes(data)
            artifact = self.register(attempt['id'], source, 'capture', logical_path=logical)
            with self.transaction():
                self._active_attempt(attempt['id'])
                imported = self._record('imports', {'id': attempt['id'], 'run_id': run['id'],
                    'artifact_id': artifact['id'], 'path': '/' + logical, 'name': Path(name).name,
                    'actor': actor, 'width': width, 'height': height})
                self._record('attempts', {'id': attempt['id'], 'run_id': run['id'],
                    'status': 'succeeded', 'reason': None}, 'outcome')
                return imported
        except BaseException as error:
            if not self._path('attempts', attempt['id'], 'outcome').exists():
                self.finish_attempt(attempt['id'], 'failed', reason=str(error) or type(error).__name__)
            raise

    def resolve_import(self, name):
        identity = imported_identity(name)
        if not identity:
            raise ValueError('Invalid managed input alias')
        imported = self._read('imports', identity)
        if imported['path'].lstrip('/') != name.lstrip('/'):
            raise ValueError('Managed input alias does not match its source')
        outcome = self._read('attempts', identity, 'outcome')
        if outcome['status'] != 'succeeded':
            raise ValueError('Managed input import did not succeed')
        artifact = self.verify_artifact(imported['artifact_id'])
        return imported, self.object_path(artifact['sha256'])

    def backup_configuration(self, data, actor):
        if not isinstance(actor, str) or not actor.strip():
            raise ValueError('Configuration backup requires actor')
        run = self.start_run({'stage': 'configuration-backup'})
        attempt = self.start_attempt(run['id'], 'configuration-backup', actor)
        source = self.work_path(attempt['id']) / 'creative.config.json'
        source.write_bytes(data)
        artifact = self.register(attempt['id'], source, 'configuration', logical_path='creative.config.json')
        self.finish_attempt(attempt['id'], 'succeeded')
        return artifact

    def discard_input(self, import_id, actor, reason):
        if not isinstance(actor, str) or not actor.strip() or not isinstance(reason, str) or not reason.strip():
            raise ValueError('Input disposition requires actor and reason')
        with self.transaction():
            self._read('imports', import_id)
            return self._record('input-dispositions', {'id': import_id, 'status': 'discarded',
                'actor': actor, 'reason': reason})

    def input_status(self, import_id):
        imported = self._read('imports', import_id)
        path = self._path('input-dispositions', import_id)
        disposition = self._read('input-dispositions', import_id) if path.exists() else None
        return {'import': imported, 'status': 'discarded' if disposition else 'active', 'disposition': disposition}

    def _live_configuration(self):
        import json
        from artifact_lifecycle import StoragePaths
        if self.config_path.exists():
            config = json.loads(self.config_path.read_text())
        elif self._explicit_config_path:
            raise ValueError('Current project configuration is missing')
        else:
            config = self.config
        if StoragePaths.resolve(self.paths.project, config).binding() != self.paths.binding():
            raise ValueError('Live configuration storage changed; relocate explicitly')
        if config.get('project', {}).get('id') != self.config.get('project', {}).get('id'):
            raise ValueError('Live project identity changed')
        return config

    def _configured_imports(self, config):
        references = set()
        def visit(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key in ('screenshot', 'source', 'imageUrl') and isinstance(item, str):
                        identity = imported_identity(item)
                        if identity:
                            references.add(identity)
                    visit(item)
            elif isinstance(value, list):
                for item in value:
                    visit(item)
        visit(config)
        return references
