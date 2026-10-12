"""Shared local Studio input, persistence, and render-evidence contracts."""
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import threading
import zlib

WRITE_LOCK = threading.RLock()
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$")
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_PIXELS = 40_000_000


def digest(data):
    return hashlib.sha256(data).hexdigest()


def revision(path):
    return '"' + (digest(path.read_bytes()) if path.exists() else 'missing') + '"'


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.' + path.name, delete=False) as out:
        temporary = Path(out.name)
        out.write((json.dumps(data, indent=2, ensure_ascii=False) + '\n').encode())
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def check_copy(fields, label):
    if not isinstance(fields, dict):
        raise ValueError(f"{label} must be an object")
    for field in ('headline', 'subheadline', 'screenshot', 'layout'):
        if field in fields and not isinstance(fields[field], str):
            raise ValueError(f"{label}.{field} must be text")
    if 'inheritDefault' in fields and not isinstance(fields['inheritDefault'], bool):
        raise ValueError(f"{label}.inheritDefault must be a boolean")
    if 'deviceOffset' in fields:
        offset = fields['deviceOffset']
        if not isinstance(offset, dict) or any(isinstance(v, bool) or not isinstance(v, (int, float))
                                              or not math.isfinite(v) for v in offset.values()):
            raise ValueError(f"{label}.deviceOffset requires finite numeric values")


def check_localizations(values, label):
    if not isinstance(values, dict):
        raise ValueError(f"{label} must be an object")
    for locale, fields in values.items():
        check_copy(fields, f"{label}.{locale}")


def check_background(value, label):
    if not isinstance(value, dict) or not isinstance(value.get('type'), str):
        raise ValueError(f"{label} requires a background type")
    if 'colors' in value and (not isinstance(value['colors'], list) or
                              any(not isinstance(color, str) for color in value['colors'])):
        raise ValueError(f"{label}.colors must be a list of text colors")
    if 'imageUrl' in value and not isinstance(value['imageUrl'], str):
        raise ValueError(f"{label}.imageUrl must be text")


def check_config(config):
    if not isinstance(config, dict) or not isinstance(config.get('cards'), list):
        raise ValueError("Configuration requires a cards array")
    for field in ('project',):
        if not isinstance(config.get(field), dict):
            raise ValueError(f'Configuration requires a {field} object')
    for field in ('project', 'theme', 'studio', 'localizations'):
        if field in config and not isinstance(config[field], dict):
            raise ValueError(f"Configuration {field} must be an object")
    for field in ('id', 'name', 'bundleId', 'defaultLocale'):
        if field in config.get('project', {}) and not isinstance(config['project'][field], str):
            raise ValueError(f"Project {field} must be text")
    theme = config.get('theme', {})
    if 'background' in theme:
        check_background(theme['background'], 'theme.background')
    if 'fontFamily' in theme and not isinstance(theme['fontFamily'], str):
        raise ValueError('Theme fontFamily must be text')
    for locale, cards in config.get('localizations', {}).items():
        check_localizations(cards, f'localizations.{locale}')
    identifiers = [c.get('id') for c in config['cards'] if isinstance(c, dict)]
    if len(identifiers) != len(config['cards']) or any(not isinstance(x, str) or not SAFE_ID.fullmatch(x) for x in identifiers):
        raise ValueError("Cards require safe, stable IDs")
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Card IDs must be unique")
    for values, label in ((config.get('targets', ['iphone_6_9']), 'targets'),
                          (config.get('project', {}).get('locales', ['en-US']), 'locales')):
        if not isinstance(values, list) or not values or any(not isinstance(x, str) or not SAFE_ID.fullmatch(x) for x in values) or len(set(values)) != len(values):
            raise ValueError(f"Declare a nonempty list of unique safe {label}")
    default = config.get('project', {}).get('defaultLocale', 'en-US')
    if default not in config.get('project', {}).get('locales', ['en-US']):
        raise ValueError('Default language must be declared in project locales')
    for card in config['cards']:
        check_copy(card, f"cards.{card['id']}")
        if 'customBackground' in card:
            check_background(card['customBackground'], f"cards.{card['id']}.customBackground")
        if config.get('studio', {}).get('requireExportEvidence') and not isinstance(card.get('headline'), str):
            raise ValueError(f"Card {card['id']} requires a text headline")
        if 'variants' in card and not isinstance(card['variants'], dict):
            raise ValueError(f"Card {card['id']} variants must be an object")
        for variant in card.get('variants', {}).values():
            check_copy(variant, f"cards.{card['id']}.variant")
            check_localizations(variant.get('localizations', {}), f"cards.{card['id']}.variant.localizations")
    if len(config['cards']) > 100:
        raise ValueError("Studio supports at most 100 cards per project")
    if config.get('studio', {}).get('requireExportEvidence'):
        for field in ('id', 'name', 'bundleId'):
            if not isinstance(config.get('project', {}).get(field), str) or not config['project'][field].strip():
                raise ValueError(f"Project {field} is required")
        if not isinstance(config.get('theme'), dict):
            raise ValueError("Project theme is required")
    return config


def resolve_card(config, card, target, locale):
    variant = card.get('variants', {}).get(target, {})
    localized = {**config.get('localizations', {}).get(locale, {}).get(card['id'], {}),
                 **variant.get('localizations', {}).get(locale, {})}
    result = {**card, **{k: v for k, v in variant.items() if k != 'localizations'}}
    result.update({k: v for k, v in localized.items() if k in ('headline', 'subheadline', 'screenshot')})
    return result, localized


def local_asset(root, name, config=None):
    if not isinstance(name, str) or not name or '://' in name or name.startswith('data:'):
        raise ValueError("Assign an existing local capture")
    from input_lifecycle import imported_identity, SNAPSHOT_INDEX
    if imported_identity(name):
        logical = name.lstrip('/')
        snapshot = root / SNAPSHOT_INDEX
        if snapshot.is_file() and not snapshot.is_symlink():
            expected = json.loads(snapshot.read_text()).get(logical)
            candidate = root / logical
            if candidate.resolve() != candidate or not candidate.is_file() or digest(candidate.read_bytes()) != expected:
                raise ValueError('Managed input snapshot integrity failure')
            return candidate
        if config is None:
            raise ValueError('Managed input resolution requires project configuration')
        from artifact_lifecycle import Lifecycle
        try:
            return Lifecycle(root, config).resolve_import(logical)[1]
        except OSError as error:
            raise ValueError('Missing managed input') from error
    path = (root / name.lstrip('/')).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError(f"Missing or escaped local capture: {name}")
    return path


def input_hashes(root, config, targets=None, locales=None):
    from input_lifecycle import imported_identity as imported_identity_for_hash
    sources = {}
    findings = []
    strict = config.get('studio', {}).get('requireExportEvidence', False)
    for locale in locales or config.get('project', {}).get('locales', ['en-US']):
        for target in targets or config.get('targets', ['iphone_6_9']):
            for card in config['cards']:
                resolved, localized = resolve_card(config, card, target, locale)
                label = f"{locale}/{target}/{card['id']}"
                try:
                    if strict and locale != config.get('project', {}).get('defaultLocale', 'en-US'):
                        required = ['headline'] + ([] if resolved.get('layout') == 'pure_text' else ['screenshot'])
                        if any(field not in localized for field in required) and not localized.get('inheritDefault'):
                            raise ValueError("Review inherited copy/capture or assign a localized version")
                    if strict and target.startswith('mac_') and any(t.startswith('iphone_') for t in config.get('targets', [])):
                        variant = card.get('variants', {}).get(target, {})
                        if resolved.get('layout') != 'pure_text' and not variant.get('screenshot') and not variant.get('localizations', {}).get(locale, {}).get('screenshot'):
                            raise ValueError("Assign a desktop capture for the desktop composition")
                    if resolved.get('layout') != 'pure_text':
                        name = resolved.get('screenshot')
                        if name or strict:
                            path = local_asset(root, name, config)
                            sources[name.lstrip('/') if imported_identity_for_hash(name) else str(path.relative_to(root.resolve()))] = digest(path.read_bytes())
                    bg = resolved.get('customBackground', config.get('theme', {}).get('background', {}))
                    if bg.get('type') == 'image':
                        name = bg.get('imageUrl')
                        path = local_asset(root, name, config)
                        sources[name.lstrip('/') if imported_identity_for_hash(name) else str(path.relative_to(root.resolve()))] = digest(path.read_bytes())
                except ValueError as error:
                    findings.append(f"{label}: {error}")
    return sources, findings


def inspect_png(data):
    """Validate all chunks and decompressed scanlines, not just the PNG header."""
    if len(data) > MAX_IMAGE_BYTES or not data.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError("Invalid or oversized PNG")
    offset, compressed, header, alpha, ended = 8, bytearray(), None, False, False
    while offset + 12 <= len(data):
        size = int.from_bytes(data[offset:offset + 4], 'big')
        kind = data[offset + 4:offset + 8]
        end = offset + 12 + size
        if end > len(data):
            raise ValueError("Truncated PNG chunk")
        payload = data[offset + 8:offset + 8 + size]
        if zlib.crc32(kind + payload) & 0xffffffff != int.from_bytes(data[end - 4:end], 'big'):
            raise ValueError("Corrupt PNG checksum")
        if kind == b'IHDR':
            if header is not None or offset != 8 or size != 13:
                raise ValueError("Invalid PNG header")
            header = struct.unpack('>IIBBBBB', payload)
        elif kind == b'IDAT':
            compressed.extend(payload)
        elif kind == b'tRNS':
            alpha = True
        elif kind == b'IEND':
            ended = True
            if size or end != len(data):
                raise ValueError("Invalid PNG ending")
            break
        offset = end
    if not header or not ended or not compressed:
        raise ValueError("Incomplete PNG")
    width, height, depth, color, compression, filtering, interlace = header
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color)
    if not channels or not width or not height or width * height > MAX_PIXELS or compression or filtering:
        raise ValueError("Unsupported or oversized PNG")
    if depth not in (1, 2, 4, 8, 16) or (color in (2, 4, 6) and depth not in (8, 16)):
        raise ValueError("Invalid PNG bit depth")
    if interlace:
        raise ValueError("Interlaced PNG: re-export the capture as a standard PNG")
    stride = (width * channels * depth + 7) // 8 + 1
    decoder = zlib.decompressobj()
    raw = decoder.decompress(bytes(compressed), stride * height + 1)
    if len(raw) != stride * height or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise ValueError("Corrupt PNG pixel data")
    if any(raw[row * stride] > 4 for row in range(height)):
        raise ValueError("Invalid PNG scanline")
    return width, height, alpha or color in (4, 6)


def inspect_capture(data):
    if data.startswith(b'\x89PNG'):
        return (*inspect_png(data)[:2], 'png')
    if len(data) > MAX_IMAGE_BYTES or not data.startswith(b'\xff\xd8') or not data.endswith(b'\xff\xd9'):
        raise ValueError("Use a valid PNG or JPEG capture (up to 20 MB)")
    if not shutil.which('sips'):
        raise ValueError("JPEG decoding unavailable; import a PNG capture instead")
    with tempfile.TemporaryDirectory() as directory:
        source, decoded = Path(directory) / 'capture.jpg', Path(directory) / 'decoded.png'
        source.write_bytes(data)
        result = subprocess.run(['sips', '-s', 'format', 'png', str(source), '--out', str(decoded)], capture_output=True, timeout=15)
        if result.returncode or not decoded.exists():
            raise ValueError("Could not decode JPEG capture")
        width, height, _ = inspect_png(decoded.read_bytes())
        return width, height, 'jpeg'
