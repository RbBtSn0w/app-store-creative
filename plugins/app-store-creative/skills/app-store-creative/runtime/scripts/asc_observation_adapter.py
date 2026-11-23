"""Normalize official ASC preview-list facts; never execute remote operations."""
import re

_DELIVERY_STATES = ('COMPLETE', 'FAILED', 'PROCESSING', 'UPLOADING')
# Apple's in-flight media states, folded into the lifecycle vocabulary.
_IN_FLIGHT_STATES = {'AWAITING_UPLOAD': 'UPLOADING', 'UPLOAD_COMPLETE': 'PROCESSING'}


def _delivery_state(attributes, field):
    state = attributes.get(field)
    if state is None:
        return None
    if not isinstance(state, dict):
        raise ValueError('Invalid ASC delivery state')
    value = state.get('state')
    if value in _DELIVERY_STATES:
        return value
    return _IN_FLIGHT_STATES.get(value, 'UNKNOWN')


def _preview_processing(attributes):
    """Combine file delivery with video transcoding.

    `assetDeliveryState` reaches COMPLETE as soon as the upload lands, while
    `videoDeliveryState` stays PROCESSING with an empty `videoUrl` until Apple
    finishes transcoding, so only the video state plus a URL establish completion.
    The deprecated asset state may be absent from API 3.7+ responses.
    """
    asset = _delivery_state(attributes, 'assetDeliveryState')
    video = _delivery_state(attributes, 'videoDeliveryState')
    url = attributes.get('videoUrl')
    if url is not None and not isinstance(url, str):
        raise ValueError('Invalid ASC video URL')
    if 'FAILED' in (asset, video):
        return 'FAILED'
    if asset not in (None, 'COMPLETE'):
        return asset
    if video is None:
        return 'UNKNOWN'
    if video != 'COMPLETE':
        return video
    return 'COMPLETE' if url else 'PROCESSING'


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
    result = {'upload': upload, 'processing': {'processing_state': _preview_processing(attributes)}}
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


def media_response(plan, response, scope):
    target = plan['target']
    if target.get('kind') != 'customProductPageVersion':
        return response
    localization_fields = [response[key] for key in ('customProductPageLocalizationId', 'localizationId')
                           if key in response]
    if (target.get('cpp_localization_id') != scope['localization_id']
            or localization_fields != [scope['localization_id']] or 'versionLocalizationId' in response):
        raise ValueError('CPP evidence localization differs from the approved target')
    selected = next(asset for asset in plan['assets'] if asset['artifact_id'] == scope['artifact_id'])
    role = selected['role']
    expected_id = target['set_ids'].get(role)
    display_field = 'screenshotDisplayType' if role == 'screenshot' else 'previewType'
    expected_display = target['display_type']
    if role == 'preview' and target['target'] == 'iphone_6_9':
        expected_display = 'IPHONE_67'
    bound = []
    for item in response['sets']:
        remote_set = item['set']
        relationships = remote_set.get('relationships', {})
        parent = relationships.get('appCustomProductPageLocalization', {}).get('data')
        if parent and parent.get('id') != scope['localization_id']:
            raise ValueError('Foreign CPP media set localization')
        if any(relationships.get(k, {}).get('data') for k in
               ('appStoreVersionLocalization', 'appStoreVersionExperimentTreatmentLocalization')):
            raise ValueError('Foreign CPP media set parent')
        display = remote_set.get('attributes', {}).get(display_field, '').removeprefix('APP_')
        if expected_id:
            if remote_set['id'] == expected_id:
                bound.append(item)
        elif display == expected_display:
            bound.append(item)
    if len(bound) != 1:
        raise ValueError('Could not identify one matching CPP media set')
    return {**response, 'versionLocalizationId': scope['localization_id'], 'sets': bound}


def preview_observations(plan, response, scope):
    """Prepare observations from an explicit ASC executor scope, without writes."""
    from record_primitives import canonical
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
                or value.startswith('/')
                or re.search(r'(?:https?|file):', value, re.IGNORECASE)):
            raise ValueError('ASC executor references must be sanitized identities')
    observed = datetime.fromisoformat(scope['observed_at'])
    if observed.tzinfo is None or observed > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise ValueError('ASC observation time must be timezone-aware and not in the future')
    facts = preview_facts(media_response(plan, response, scope), scope['localization_id'], scope['remote_id'])
    binding = {'plan_sha256': hashlib.sha256(canonical(plan)).hexdigest(),
               'target': plan['target'], 'artifact_id': scope['artifact_id'],
               'remote_id': scope['remote_id'], 'source': 'asc-cli',
               'observed_at': scope['observed_at'], 'evidence_reference': scope['evidence_reference'],
               'evidence_sha256': hashlib.sha256(response_bytes).hexdigest()}
    return [{**binding, 'gate': gate, 'facts': values} for gate, values in facts.items()]


video_facts = preview_facts
video_observations = preview_observations


def screenshot_facts(response, localization_id, remote_id):
    """Select an explicit remote screenshot resource within an executor-resolved localization.

    The executor must independently bind the localization to the publication
    target. A URL or positive dimensions cannot prove image display.
    """
    if not isinstance(response, dict) or response.get('versionLocalizationId') != localization_id:
        raise ValueError('ASC response localization differs from the requested scope')
    sets = response.get('sets')
    if not isinstance(sets, list):
        raise ValueError('Invalid ASC screenshot sets')
    matches = []
    for item in sets:
        if not isinstance(item, dict) or not isinstance(item.get('screenshots'), list):
            raise ValueError('Invalid ASC screenshot list')
        for resource in item['screenshots']:
            if not isinstance(resource, dict) or resource.get('type') != 'appScreenshots':
                raise ValueError('Invalid ASC screenshot resource')
            if resource.get('id') == remote_id:
                matches.append(resource)
    if len(matches) > 1:
        raise ValueError('Duplicate ASC remote screenshot identity')
    if not matches:
        return {'upload': {'found': False}}
    attributes = matches[0].get('attributes')
    if not isinstance(attributes, dict):
        raise ValueError('Invalid ASC screenshot attributes')
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
    image = attributes.get('imageAsset')
    if image is not None:
        if not isinstance(image, dict):
            raise ValueError('Invalid ASC screenshot image asset')
        media = {}
        for field in ('width', 'height'):
            value = image.get(field)
            if value is not None:
                if type(value) is not int or value < 0:
                    raise ValueError('Invalid ASC screenshot dimensions')
                media['image_' + field] = value
        if any(media.get('image_' + field) == 0 for field in ('width', 'height')):
            media['media_verified'] = False
        if media:
            result['media'] = media
    return result


def screenshot_observations(plan, response, scope):
    """Prepare screenshot observations from an explicit ASC executor scope, without writes."""
    from record_primitives import canonical
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
    if not asset or asset['role'] != 'screenshot':
        raise ValueError('Screenshot artifact is outside publication scope')
    for key in ('localization_id', 'remote_id', 'evidence_reference'):
        value = scope[key]
        if (not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,256}', value)
                or value.startswith('/')
                or re.search(r'(?:https?|file):', value, re.IGNORECASE)):
            raise ValueError('ASC executor references must be sanitized identities')
    observed = datetime.fromisoformat(scope['observed_at'])
    if observed.tzinfo is None or observed > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise ValueError('ASC observation time must be timezone-aware and not in the future')
    facts = screenshot_facts(media_response(plan, response, scope), scope['localization_id'], scope['remote_id'])
    binding = {'plan_sha256': hashlib.sha256(canonical(plan)).hexdigest(),
               'target': plan['target'], 'artifact_id': scope['artifact_id'],
               'remote_id': scope['remote_id'], 'source': 'asc-cli',
               'observed_at': scope['observed_at'], 'evidence_reference': scope['evidence_reference'],
               'evidence_sha256': hashlib.sha256(response_bytes).hexdigest()}
    return [{**binding, 'gate': gate, 'facts': values} for gate, values in facts.items()]
