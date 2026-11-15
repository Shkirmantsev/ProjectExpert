"""Versioned image descriptors; pixels and absolute locators remain local."""
from .portable_format import encode, sha

IMAGE_PROJECTION = 'gemma-image-v1'


def pipeline_key(source, driver):
    return sha(encode({'mediaProjection': IMAGE_PROJECTION})) if source.family == 'image' else driver.pipeline_key(source)


def image_descriptor(source):
    from dataclasses import asdict
    path = source.metadata.sourcePath
    text = 'Image: ' + path
    return {'kind': 'media_source', 'id': sha(('image:' + path).encode()),
            'sourceId': source.id, 'contentHash': source.contentHash,
            'projection': IMAGE_PROJECTION, 'metadata': asdict(source.metadata),
            'retrievalText': text,
            'retrievalTextHash': sha((text + source.contentHash + IMAGE_PROJECTION).encode())}


def persist_image(cache, source, driver):
    from pi_platform.core.canonical import to_canonical_json, content_address
    key = pipeline_key(source, driver)
    metadata = content_address(to_canonical_json(source.metadata).decode())
    if cache.source_record(source.id) is not None:
        return
    raw = encode(image_descriptor(source))
    address = sha(raw)
    summary = encode({'addresses': [address], 'chunkCount': 0, 'entityCount': 0,
                      'relationCount': 0, 'evidenceCount': 0, 'mediaCount': 1,
                      'knowledgeState': 'verified', 'degraded': False})
    cache.complete_source_atomic(source.id, source.contentHash, key, (address,), metadata,
                                 {address: raw, key: summary})
