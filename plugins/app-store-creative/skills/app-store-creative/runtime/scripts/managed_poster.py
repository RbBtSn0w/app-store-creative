"""Extract a selected preview frame under the shared artifact lifecycle."""
import json
import math
import re
from pathlib import Path
import subprocess
from artifact_lifecycle import canonical


def timestamp_from_time_code(value, fps):
    if (not isinstance(value, str) or not re.fullmatch(r'\d{2}:\d{2}:\d{2}:\d{2}', value)
            or isinstance(fps, bool) or not isinstance(fps, (int, float))
            or not math.isfinite(fps) or not 0 < fps <= 30):
        raise ValueError('Poster requires an HH:MM:SS:FF time code and valid preview fps')
    hours, minutes, seconds, frames = map(int, value.split(':'))
    if minutes >= 60 or seconds >= 60 or frames >= fps:
        raise ValueError('Poster time code is outside the preview frame rate')
    return hours * 3600 + minutes * 60 + seconds + frames / fps


def extract(source, output, timestamp):
    from media_tool_identity import MediaTools
    tools = MediaTools()
    probe = json.loads(subprocess.run([tools.paths['ffprobe'], '-v', 'error', '-show_streams',
        '-show_format', '-of', 'json', str(source)], check=True, capture_output=True,
        text=True, timeout=30).stdout)
    videos = [item for item in probe['streams'] if item.get('codec_type') == 'video']
    duration = float(probe['format']['duration'])
    if len(videos) != 1 or not math.isfinite(duration) or timestamp >= duration:
        raise ValueError('Poster timestamp must address a single finite video stream')
    subprocess.run([tools.paths['ffmpeg'], '-hide_banner', '-loglevel', 'error', '-i', str(source),
        '-ss', str(timestamp), '-frames:v', '1', '-an', '-n', str(output)],
        check=True, capture_output=True, timeout=60)
    subprocess.run([tools.paths['ffmpeg'], '-hide_banner', '-loglevel', 'error', '-xerror', '-i',
        str(output), '-f', 'null', '-'], check=True, capture_output=True, timeout=30)
    frame = json.loads(subprocess.run([tools.paths['ffprobe'], '-v', 'error', '-show_streams',
        '-of', 'json', str(output)], check=True, capture_output=True, text=True,
        timeout=30).stdout)['streams']
    if (len(frame) != 1 or frame[0]['codec_name'] != 'png'
            or frame[0]['width'] != videos[0]['width'] or frame[0]['height'] != videos[0]['height']):
        raise ValueError('Poster frame is not a decodable PNG matching the video')
    tools.verify()
    return {'tools': tools.evidence, 'width': videos[0]['width'], 'height': videos[0]['height'], 'duration': duration}


def produce(core, run_id, preview_id, timestamp, owner, retry_of=None):
    if isinstance(timestamp, bool) or not math.isfinite(timestamp) or timestamp < 0:
        raise ValueError('Poster timestamp must be finite and nonnegative')
    source = core.verify_artifact(preview_id)
    outcome = core._path('attempts', source['attempt_id'], 'outcome')
    if (source['role'] != 'preview' or source['partial'] or not outcome.exists()
            or core._read('attempts', source['attempt_id'], 'outcome')['status'] != 'succeeded'):
        raise ValueError('Poster requires a completed preview artifact')
    if retry_of:
        previous = core._read('attempts', retry_of, 'started')
        outcome_path = core._path('attempts', retry_of, 'outcome')
        if (previous['run_id'] != run_id or previous['stage'] != 'poster' or not outcome_path.exists()
                or core._read('attempts', retry_of, 'outcome')['status'] not in ('failed', 'cancelled', 'interrupted')):
            raise ValueError('Poster retry requires an unsuccessful terminal poster attempt in the same run')
    attempt = core.start_attempt(run_id, 'poster', owner, retry_of=retry_of)
    work = Path(attempt['work_path']); output = work / 'poster.png'
    dependencies = [preview_id]
    try:
        with core.keep_lease(attempt['id']):
            plan_path = work / 'poster-plan.json'
            plan_path.write_bytes(canonical({'schema_version':1, 'kind':'preview-poster-plan',
                'source_artifact_id':preview_id, 'source_sha256':source['sha256'],
                'timestamp_seconds':timestamp, 'output':'media/preview/poster.png'}))
            plan = core.register(attempt['id'], plan_path, 'source', inputs=[preview_id],
                                 logical_path='evidence/poster-plan.json')
            dependencies.append(plan['id'])
            media = extract(core.object_path(source['sha256']), output, timestamp)
            receipt_path = work / 'poster-receipt.json'
            receipt_path.write_bytes(canonical({'schema_version':1, 'kind':'preview-poster',
                'source_artifact_id':preview_id, 'source_sha256':source['sha256'],
                'timestamp_seconds':timestamp, 'media':media, 'output':'media/preview/poster.png',
                'uploaded':False, 'visual_approval_granted':False}))
            receipt = core.register(attempt['id'], receipt_path, 'producer-evidence',
                inputs=dependencies, logical_path='evidence/poster-receipt.json')
            poster = core.register(attempt['id'], output, 'poster',
                inputs=dependencies + [receipt['id']], logical_path='preview/poster.png')
            core.finish_attempt(attempt['id'], 'succeeded')
            return {'run_id':run_id, 'attempt_id':attempt['id'], 'status':'succeeded',
                    'poster_artifact_id':poster['id'], 'evidence_artifact_id':receipt['id'],
                    'approval_granted':False}
    except BaseException as error:
        try:
            if output.is_file():
                core.register(attempt['id'], output, 'poster', partial=True,
                    inputs=dependencies, logical_path='preview/poster.png')
            core.finish_attempt(attempt['id'], 'cancelled' if isinstance(error, KeyboardInterrupt)
                                else 'failed', str(error) or type(error).__name__)
        except Exception as evidence_error:
            error.add_note('Could not finish poster evidence: ' + str(evidence_error))
        raise
