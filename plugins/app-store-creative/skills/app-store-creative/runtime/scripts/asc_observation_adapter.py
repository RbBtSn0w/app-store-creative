"""Normalize official ASC preview-list facts; never execute remote operations."""
import re


def preview_facts(response, localization_id, remote_id):
    """Select an explicit remote resource within an executor-resolved localization.

    The executor must independently bind the localization to the publication
    target. A URL or positive dimensions cannot prove playback or image loading.
    """
    if not isinstance(response, dict) or response.get('versionLocalizationId') != localization_id:
        raise ValueError('ASC response localization differs from the requested scope')
    sets = response.get('sets')
    if not isinstance(sets, list):
        raise ValueError('Invalid ASC preview sets')
    matches = []
    for item in sets:
        if not isinstance(item, dict) or not isinstance(item.get('previews'), list):
            raise ValueError('Invalid ASC preview list')
        for resource in item['previews']:
            if not isinstance(resource, dict) or resource.get('type') != 'appPreviews':
                raise ValueError('Invalid ASC preview resource')
            if resource.get('id') == remote_id:
                matches.append(resource)
    if len(matches) > 1:
        raise ValueError('Duplicate ASC remote preview identity')
    if not matches:
        return {'upload': {'found': False}}
    attributes = matches[0].get('attributes')
    if not isinstance(attributes, dict):
        raise ValueError('Invalid ASC preview attributes')
    upload = {'found': True}
    checksum = attributes.get('sourceFileChecksum')
    if checksum is not None:
        if not isinstance(checksum, str) or not re.fullmatch(r'[0-9a-f]{32}', checksum):
            raise ValueError('Invalid ASC source checksum')
        upload['source_checksum'] = checksum
    state = attributes.get('assetDeliveryState') or {}
    if not isinstance(state, dict):
        raise ValueError('Invalid ASC delivery state')
    processing = state.get('state')
    result = {'upload': upload, 'processing': {'processing_state': processing
        if processing in ('COMPLETE', 'FAILED', 'PROCESSING', 'UPLOADING') else 'UNKNOWN'}}
    poster = {}
    time_code = attributes.get('previewFrameTimeCode')
    if time_code is not None:
        if not isinstance(time_code, str) or not re.fullmatch(r'[0-9:.]{1,32}', time_code):
            raise ValueError('Invalid ASC poster time code')
        poster['poster_frame_time_code'] = time_code
    image = attributes.get('previewFrameImage') or attributes.get('previewImage')
    if image is not None:
        if not isinstance(image, dict):
            raise ValueError('Invalid ASC poster image')
        for field in ('width', 'height'):
            value = image.get(field)
            if value is not None:
                if type(value) is not int or value < 0:
                    raise ValueError('Invalid ASC poster dimensions')
                poster['poster_' + field] = value
        if any(poster.get('poster_' + field) == 0 for field in ('width', 'height')):
            poster['poster_verified'] = False
    if poster:
        result['poster'] = poster
    return result


def preview_observations(plan, response, scope):
    """Prepare observations from an explicit ASC executor scope, without writes."""
    from artifact_lifecycle import canonical
    import json
    if not isinstance(response, bytes) or not response:
        raise ValueError('ASC evidence must be nonempty response bytes')
    response_bytes = response
    response = json.loads(response_bytes)
    from datetime import datetime, timezone, timedelta
    import hashlib
    fields = {'target', 'artifact_id', 'localization_id', 'remote_id',
              'observed_at', 'evidence_reference'}
    if not isinstance(scope, dict) or set(scope) != fields or scope['target'] != plan['target']:
        raise ValueError('ASC executor scope differs from publication plan')
    asset = next((a for a in plan['assets'] if a['artifact_id'] == scope['artifact_id']), None)
    if not asset or asset['role'] != 'preview':
        raise ValueError('Preview artifact is outside publication scope')
    for key in ('localization_id', 'remote_id', 'evidence_reference'):
        value = scope[key]
        if (not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,256}', value)
                or value.startswith(('/', 'file:', 'http:', 'https:'))):
            raise ValueError('ASC executor references must be sanitized identities')
    observed = datetime.fromisoformat(scope['observed_at'])
    if observed.tzinfo is None or observed > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise ValueError('ASC observation time must be timezone-aware and not in the future')
    facts = preview_facts(response, scope['localization_id'], scope['remote_id'])
    binding = {'plan_sha256': hashlib.sha256(canonical(plan)).hexdigest(),
               'target': plan['target'], 'artifact_id': scope['artifact_id'],
               'remote_id': scope['remote_id'], 'source': 'asc-cli',
               'observed_at': scope['observed_at'], 'evidence_reference': scope['evidence_reference'],
               'evidence_sha256': hashlib.sha256(response_bytes).hexdigest()}
    return [{**binding, 'gate': gate, 'facts': values} for gate, values in facts.items()]
