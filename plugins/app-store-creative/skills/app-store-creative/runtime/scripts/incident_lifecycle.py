"""Immutable operational incidents and their protected evidence references."""


class IncidentOperations:
    def open_incident(self, actor, reason, artifacts=None, candidates=None, deliveries=None):
        from artifact_lifecycle import identifier
        if not isinstance(actor, str) or not actor.strip() or not isinstance(reason, str) or not reason.strip():
            raise ValueError('Incident requires actor and reason')
        references = {'artifacts': artifacts or [], 'candidates': candidates or [], 'deliveries': deliveries or []}
        if not any(references.values()):
            raise ValueError('Incident requires evidence references')
        with self.transaction():
            for category, identities in references.items():
                if not isinstance(identities, list) or len(set(identities)) != len(identities):
                    raise ValueError('Incident references must be unique lists')
                for identity in identities:
                    self._read(category, identity)
            return self._record('incidents', {'id': identifier(), 'actor': actor,
                'reason': reason, **references})

    def close_incident(self, incident_id, actor, resolution):
        if not isinstance(actor, str) or not actor.strip() or not isinstance(resolution, str) or not resolution.strip():
            raise ValueError('Incident closure requires actor and resolution')
        with self.transaction():
            self._read('incidents', incident_id)
            return self._record('incidents', {'id': incident_id, 'status': 'closed',
                'actor': actor, 'resolution': resolution}, 'resolution')

    def incident_status(self, incident_id):
        incident = self._read('incidents', incident_id)
        resolution = self._path('incidents', incident_id, 'resolution')
        closed = self._read('incidents', incident_id, 'resolution') if resolution.exists() else None
        return {'incident': incident, 'status': 'closed' if closed else 'open', 'resolution': closed}

    def _incident_artifacts(self):
        protected = set()
        for path in (self.paths.workspace / 'records/incidents').glob('*.json'):
            incident = self._read('incidents', path.stem)
            if self._path('incidents', path.stem, 'resolution').exists():
                self._read('incidents', path.stem, 'resolution')
                continue
            protected.update(incident['artifacts'])
            candidates = set(incident['candidates'])
            for identity in incident['deliveries']:
                candidates.add(self._read('deliveries', identity)['candidate_id'])
            for identity in candidates:
                protected.update(self._read('candidates', identity)['artifacts'])
        return protected
