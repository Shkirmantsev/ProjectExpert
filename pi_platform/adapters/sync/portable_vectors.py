"""Exact float32 text mirror; runtime profile validation remains authoritative."""
from dataclasses import asdict
import math
import re
from .portable_format import PortableSnapshotError
from pi_platform.core.retrieval.semantic_index_service import encode_vector_payload, decode_vector_payload
from pi_platform.ports.runtime.vector_record_store import VectorRecord


def encode_record(record):
    body = asdict(record)
    body.pop('created_at')
    body.pop('vector_payload')
    body['encoding'] = 'float32-roundtrip-json'
    body['vector'] = decode_vector_payload(record.vector_payload)
    decoded = decode_record(body)
    if decoded.vector_payload != record.vector_payload:
        raise PortableSnapshotError('Vector float32 roundtrip failed')
    return body


def decode_record(body):
    values = body.get('vector', [])
    dimension = body.get('dimension')
    if (body.get('encoding') != 'float32-roundtrip-json' or type(dimension) is not int
            or not 1 <= dimension <= 65536 or len(values) != dimension
            or any(type(x) not in {float, int} or not math.isfinite(x) for x in values)
            or body.get('normalization') not in {'l2', 'none'}):
        raise PortableSnapshotError('Invalid portable vector encoding/dimension/components')
    if body['normalization'] == 'l2' and abs(sum(x*x for x in values) - 1) >= 0.02:
        raise PortableSnapshotError('Invalid portable vector normalization')
    for key in ('embedding_profile_hash', 'created_from_retrieval_text_hash'):
        if not re.fullmatch('[a-f0-9]{64}', body.get(key, '')):
            raise PortableSnapshotError('Invalid portable vector profile/text hash')
    try:
        payload = encode_vector_payload(values)
        if any(not math.isfinite(x) for x in decode_vector_payload(payload)):
            raise ValueError('Float32 overflow')
        return VectorRecord(**{key: body[key] for key in VectorRecord.__dataclass_fields__
                              if key not in {'created_at', 'vector_payload'}}, vector_payload=payload)
    except (ValueError, TypeError, OverflowError) as exc:
        raise PortableSnapshotError('Invalid float32 portable vector') from exc
