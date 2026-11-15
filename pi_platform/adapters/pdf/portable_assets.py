"""Text figure provenance and bounded, exact-hash page regeneration."""
from importlib.metadata import PackageNotFoundError, version
import io
from pathlib import Path

from pi_platform.adapters.sync.portable_format import PortableSnapshotError, confined, encode, sha


def render_profile():
    packages = {}
    for name in ('docling', 'docling-core', 'pypdfium2', 'pillow'):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = 'unavailable'
    return sha(encode({'packages': packages, 'imagesScale': 1.0, 'imageFormat': 'PNG',
                       'profile': 'docling-picture/1'}))


def validate_descriptor(value):
    import math
    import re
    from pi_platform.adapters.sync.portable_format import source_path
    required = {'schema', 'sourcePath', 'sourceHash', 'assetId', 'byteHash', 'page', 'bbox', 'renderProfile', 'strategyVersion'}
    if not isinstance(value, dict) or set(value) != required or value['schema'] != 'pdf-figure/1':
        raise PortableSnapshotError('Invalid portable figure descriptor')
    source_path(value['sourcePath'])
    if not value['sourcePath'].lower().endswith('.pdf'):
        raise PortableSnapshotError('Figure source must be PDF')
    for key in ('sourceHash', 'byteHash', 'renderProfile'):
        if not isinstance(value[key], str) or not re.fullmatch('[a-f0-9]{64}', value[key]):
            raise PortableSnapshotError('Invalid figure content identity')
    if (not isinstance(value['assetId'], str) or not value['assetId'] or
            type(value['page']) is not int or value['page'] < 1 or
            not isinstance(value['bbox'], list) or len(value['bbox']) not in {0, 4} or
            any(type(x) not in {int, float} or not math.isfinite(x) for x in value['bbox'])):
        raise PortableSnapshotError('Invalid figure selector')
    return value


def ensure_local_asset(target, cache_root, descriptor, *, converter=None, pages=None):
    """Never trust an unverified crop; one page conversion per page per run."""
    descriptor = validate_descriptor(descriptor)
    from pi_platform.adapters.runtime.sqlite_ingestion_cache import _file_checksum
    source = confined(Path(target), descriptor['sourcePath'])
    if _file_checksum(source) != descriptor['sourceHash']:
        raise PortableSnapshotError('Figure source changed; reindex required')
    root = Path(cache_root) / 'document-assets' / 'assets'
    path = confined(root, descriptor['byteHash'])
    if path.is_file() and _file_checksum(path) == descriptor['byteHash']:
        return str(path)
    if descriptor['renderProfile'] != render_profile():
        raise PortableSnapshotError('Figure render profile differs; reindex required')
    if converter is None:
        from .real_docling import RealDoclingConverter
        converter = RealDoclingConverter()
    pages = pages if pages is not None else {}
    key = (descriptor['sourceHash'], descriptor['page'], descriptor['renderProfile'])
    if key not in pages:
        # Native layer inspection is not a full-document layout/OCR pass.
        layers = converter.inspect_pdf(str(source))
        number = descriptor['page']
        if number > len(layers):
            raise PortableSnapshotError('Figure page absent from original PDF')
        raw = converter.convert(str(source), page_range=(number, number), do_ocr=not layers[number - 1])
        figures = []
        for picture in getattr(raw, 'pictures', ()):
            from .docling_pdf_adapter import DoclingPdfAdapter
            page, bbox = DoclingPdfAdapter._provenance(picture)
            image = picture.get_image(raw)
            if image is None:
                continue
            stream = io.BytesIO()
            image.save(stream, format='PNG')
            data = stream.getvalue()
            figures.append((page, list(bbox), sha(data), data))
        pages[key] = figures
    for page, bbox, digest, data in pages[key]:
        if page == descriptor['page'] and bbox == descriptor['bbox'] and digest == descriptor['byteHash']:
            from pi_platform.core.canonical.durable_write import atomic_write_bytes
            root.mkdir(parents=True, mode=0o700, exist_ok=True)
            atomic_write_bytes(path, data)
            return str(path)
    raise PortableSnapshotError('Regenerated figure identity mismatch; reindex required')
