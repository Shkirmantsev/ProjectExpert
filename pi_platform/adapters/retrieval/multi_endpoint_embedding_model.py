"""Explicit, opt-in document embedding dispatcher for pre-authorized endpoints.

No URLs, credentials or endpoints are discovered here. Identity probes and
representative workloads belong to the caller. Tests of this adapter establish
scheduler correctness, never hardware performance or production quality.
"""
from collections import deque
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
import time
from typing import Callable, Mapping, Sequence

from pi_platform.ports.retrieval.embedding_model import (
    EmbeddingModelError, EmbeddingModelPort, EmbeddingRequest, EmbeddingRole,
)


@dataclass(frozen=True)
class EmbeddingEndpoint:
    name: str
    model: EmbeddingModelPort
    runtime_identity: str
    model_identity: str
    physical_devices: tuple[str, ...]
    # Must inspect the authorized endpoint, not return an assumed identity.
    # Underlying port transports/probes must have their own bounded deadlines.
    identity_probe: Callable[[], tuple[str, str]]

    def signature(self):
        return (self.name, self.runtime_identity, self.model_identity, self.physical_devices)


@dataclass(frozen=True)
class EndpointParityEvidence:
    endpoint_name: str
    minimum_cosine: float
    maximum_absolute_difference: float
    baseline_topk: tuple[tuple[str, ...], ...]
    candidate_topk: tuple[tuple[str, ...], ...]

    def passes(self):
        return (math.isfinite(self.minimum_cosine) and 0.999 <= self.minimum_cosine <= 1.000001
                and math.isfinite(self.maximum_absolute_difference)
                and 0 <= self.maximum_absolute_difference <= 0.01
                and len(self.baseline_topk) >= 2
                and all(row for row in self.baseline_topk)
                and self.baseline_topk == self.candidate_topk)


@dataclass(frozen=True)
class MultiEndpointEvidence:
    endpoint_signatures: tuple[tuple, ...]
    profile_hash: str
    workload_identity: str
    standalone_per_second: Mapping[str, tuple[float, ...]]
    combined_per_second: tuple[float, ...]
    parity: tuple[EndpointParityEvidence, ...]
    stage: str = 'document_embedding'
    batch_size: int = 32
    combined_topk: tuple[tuple[str, ...], ...] = ()


def _checked_endpoints(endpoints):
    endpoints=tuple(endpoints)
    if len(endpoints) < 2:
        raise EmbeddingModelError('multiendpoint dispatch requires at least two explicit endpoints')
    names=set()
    devices=set()
    models=set()
    profile=endpoints[0].model.profile()
    model_identity=endpoints[0].model_identity
    for endpoint in endpoints:
        if (not endpoint.name or endpoint.name in names or id(endpoint.model) in models
            or not endpoint.runtime_identity or not endpoint.model_identity
            or endpoint.model_identity != model_identity
            or endpoint.model.profile().identity() != profile.identity()
            or endpoint.model.dimension() != profile.output_dimension
            or endpoint.model.license_id() != endpoints[0].model.license_id()
            or not endpoint.physical_devices or any(not device for device in endpoint.physical_devices)
            or len(set(endpoint.physical_devices)) != len(endpoint.physical_devices)
            or devices.intersection(endpoint.physical_devices)):
            raise EmbeddingModelError('incompatible endpoint identities, profiles or duplicate physical devices')
        names.add(endpoint.name)
        models.add(id(endpoint.model))
        devices.update(endpoint.physical_devices)
    return endpoints, profile


def _verify_identity(endpoint, profile_hash):
    try:
        identity=endpoint.identity_probe()
    except Exception as exc:
        raise EmbeddingModelError(f'endpoint {endpoint.name!r} identity could not be verified') from exc
    if (identity != (endpoint.runtime_identity, endpoint.model_identity)
        or endpoint.model.profile().identity() != profile_hash):
        raise EmbeddingModelError(f'endpoint {endpoint.name!r} identity changed; dispatch refused')


def _vectors(endpoint, requests, profile):
    _verify_identity(endpoint, profile.identity())
    output=endpoint.model.embed_requests(requests)
    # Recheck after completion so a supervised runtime replacement cannot make
    # otherwise plausible vectors authoritative under a stale identity.
    _verify_identity(endpoint, profile.identity())
    if len(output) != len(requests):
        raise EmbeddingModelError(f'endpoint {endpoint.name!r} returned incompatible cardinality')
    checked=[]
    for vector in output:
        if (len(vector) != profile.output_dimension
            or any(isinstance(value, bool) or not isinstance(value, (int, float))
                   or not math.isfinite(value) for value in vector)):
            raise EmbeddingModelError(f'endpoint {endpoint.name!r} returned invalid vectors')
        norm=sum(value*value for value in vector)
        if not math.isfinite(norm) or norm <= 0 or (profile.normalization == 'l2' and abs(norm-1) > 0.02):
            raise EmbeddingModelError(f'endpoint {endpoint.name!r} returned invalid normalization')
        checked.append(list(vector))
    return checked


def _dispatch(endpoints, requests, profile, batch_size, max_retries):
    pending=deque((offset, requests[offset:offset+batch_size], 0)
                  for offset in range(0,len(requests),batch_size))
    output=[None]*len(requests)
    healthy=set(range(len(endpoints)))
    inflight={}
    # At most one batch per endpoint is in flight. This bounds submission memory
    # and avoids concurrently mutating one non-thread-safe model binding.
    with ThreadPoolExecutor(max_workers=len(endpoints), thread_name_prefix='embedding-endpoint') as pool:
        while pending or inflight:
            busy={item[0] for item in inflight.values()}
            for index in sorted(healthy-busy):
                if not pending:
                    break
                offset, group, attempts=pending.popleft()
                future=pool.submit(_vectors,endpoints[index],group,profile)
                inflight[future]=(index,offset,group,attempts)
            if not inflight:
                raise EmbeddingModelError('no compatible healthy endpoint remains for pending embeddings')
            done,_=wait(inflight,return_when=FIRST_COMPLETED)
            for future in done:
                index,offset,group,attempts=inflight.pop(future)
                try:
                    vectors=future.result()
                except Exception as exc:
                    healthy.discard(index)
                    if attempts >= max_retries:
                        raise EmbeddingModelError('embedding endpoint retry budget exhausted') from exc
                    pending.appendleft((offset,group,attempts+1))
                else:
                    output[offset:offset+len(group)]=vectors
    return output


def _text_requests(requests, *, role=None):
    for request in requests:
        if (request.image_path or request.audio_path or request.video_path
            or (role is not None and request.role != role)):
            raise EmbeddingModelError('multiendpoint evidence supports text document workloads only')


class MultiEndpointEmbeddingModel(EmbeddingModelPort):
    """Mix document vectors only after explicit compatible measured evidence."""
    def __init__(self, endpoints, evidence: MultiEndpointEvidence, *, batch_size=32,
                 max_retries=1, enabled=None):
        if enabled is None:
            enabled=os.environ.get('PI_EMBED_MULTI_BACKEND','0') == '1'
        if not enabled:
            raise EmbeddingModelError('multiendpoint embedding is disabled pending hardware acceptance')
        if not 1 <= batch_size <= 64 or not 0 <= max_retries < len(endpoints):
            raise ValueError('invalid multiendpoint batch or retry limits')
        self._endpoints,self._profile=_checked_endpoints(endpoints)
        if (evidence.stage != 'document_embedding' or evidence.batch_size != batch_size or not evidence.workload_identity
            or evidence.profile_hash != self._profile.identity()
            or tuple(endpoint.signature() for endpoint in self._endpoints) != evidence.endpoint_signatures):
            raise EmbeddingModelError('incompatible document workload or endpoint evidence identity')
        parity={item.endpoint_name:item for item in evidence.parity}
        if any(endpoint.name not in parity or not parity[endpoint.name].passes() for endpoint in self._endpoints[1:]):
            raise EmbeddingModelError('numerical and representative top-k parity evidence is required')
        baseline_ranking=next(iter(parity.values())).baseline_topk
        if evidence.combined_topk != baseline_ranking:
            raise EmbeddingModelError('combined representative top-k parity evidence is required')
        standalone=[]
        for endpoint in self._endpoints:
            values=evidence.standalone_per_second.get(endpoint.name,())
            if not self._valid_samples(values):
                raise EmbeddingModelError('repeated standalone throughput evidence is required')
            standalone.append(sum(values)/len(values))
            _verify_identity(endpoint,self._profile.identity())
        combined=evidence.combined_per_second
        if (not self._valid_samples(combined)
            or min(combined) <= max(max(values) for values in evidence.standalone_per_second.values())):
            raise EmbeddingModelError('measured combined throughput must exceed the fastest standalone endpoint')
        self._batch_size=batch_size
        self._max_retries=max_retries

    @staticmethod
    def _valid_samples(values):
        return len(values) >= 3 and all(isinstance(value,(int,float)) and not isinstance(value,bool)
                                       and math.isfinite(value) and value > 0 for value in values)

    def embed_requests(self, requests):
        requests=list(requests)
        if not requests:
            return []
        _text_requests(requests)
        if any(request.role != EmbeddingRole.DOCUMENT for request in requests):
            # Document throughput evidence cannot authorize query scheduling.
            return _vectors(self._endpoints[0],requests,self._profile)
        return _dispatch(self._endpoints,requests,self._profile,self._batch_size,self._max_retries)

    def embed_request(self, request):
        return self.embed_requests([request])[0]

    def embed(self, text):
        return self.embed_request(EmbeddingRequest(text,EmbeddingRole.DOCUMENT))

    def embed_batch(self, texts):
        return self.embed_requests([EmbeddingRequest(text,EmbeddingRole.DOCUMENT) for text in texts])

    def profile(self):
        return self._profile

    def dimension(self):
        return self._profile.output_dimension

    def model_version(self):
        return self._profile.identity()

    def license_id(self):
        return self._endpoints[0].model.license_id()

    def stats(self):
        return {'endpoints':len(self._endpoints),'batch_size':self._batch_size}


def benchmark_document_endpoints(endpoints, documents: Sequence[EmbeddingRequest],
                                 queries: Sequence[EmbeddingRequest], *, top_k=3,
                                 repetitions=3, batch_size=32, clock=time.perf_counter):
    """Measure an explicitly supplied representative text corpus on real ports.

    No source text/vectors leave this call. The returned identity hashes the
    exact role/task/title/text workload. Throughput is actual completed corpus
    work/sec, including adapter request shaping and vector validation. Callers
    own representative corpus selection and external relevance acceptance.
    """
    endpoints,profile=_checked_endpoints(endpoints)
    documents,queries=tuple(documents),tuple(queries)
    if len(documents) < max(2,batch_size*(len(endpoints)-1)+1) or len(queries) < 2 or repetitions < 3 or not 1 <= batch_size <= 64 or top_k < 1:
        raise ValueError('representative documents/queries and at least three repetitions are required')
    _text_requests(documents,role=EmbeddingRole.DOCUMENT)
    _text_requests(queries,role=EmbeddingRole.QUERY)
    identity=hashlib.sha256(json.dumps({'documents':[asdict(item) for item in documents],
        'queries':[asdict(item) for item in queries], 'top_k':top_k,'batch_size':batch_size,
        'version':'document-endpoint-benchmark/v1'},sort_keys=True).encode()).hexdigest()
    def embed(endpoint, requests):
        output=[]
        for offset in range(0,len(requests),batch_size):
            output.extend(_vectors(endpoint,requests[offset:offset+batch_size],profile))
        return output
    def normalized(vector):
        norm=math.sqrt(sum(value*value for value in vector))
        return [value/norm for value in vector]
    def ranking(doc_vectors, query_vectors):
        return tuple(tuple(str(index) for index in sorted(range(len(doc_vectors)),
            key=lambda index:(-sum(a*b for a,b in zip(query,doc_vectors[index])),index))[:top_k])
            for query in query_vectors)
    baseline_docs=[normalized(vector) for vector in embed(endpoints[0],documents)]
    baseline_queries=[normalized(vector) for vector in embed(endpoints[0],queries)]
    baseline=baseline_docs+baseline_queries
    baseline_topk=ranking(baseline_docs,baseline_queries)
    parity=[]
    for endpoint in endpoints[1:]:
        docs=[normalized(vector) for vector in embed(endpoint,documents)]
        query_vectors=[normalized(vector) for vector in embed(endpoint,queries)]
        candidate=docs+query_vectors
        item=EndpointParityEvidence(endpoint.name,
            min(sum(a*b for a,b in zip(left,right)) for left,right in zip(baseline,candidate)),
            max(abs(a-b) for left,right in zip(baseline,candidate) for a,b in zip(left,right)),
            baseline_topk,ranking(docs,baseline_queries))
        if not item.passes():
            raise EmbeddingModelError('representative document numerical or top-k parity failed')
        parity.append(item)
    def rate(operation):
        started=clock()
        operation()
        elapsed=clock()-started
        if not math.isfinite(elapsed) or elapsed <= 0:
            raise EmbeddingModelError('invalid document benchmark duration')
        return len(documents)/elapsed
    standalone={endpoint.name:tuple(rate(lambda:embed(endpoint,documents)) for _ in range(repetitions))
                for endpoint in endpoints}
    mixed=[normalized(vector) for vector in _dispatch(endpoints,documents,profile,batch_size,0)]
    combined_topk=ranking(mixed,baseline_queries)
    if combined_topk != baseline_topk:
        raise EmbeddingModelError('combined representative top-k parity failed')
    combined=tuple(rate(lambda:_dispatch(endpoints,documents,profile,batch_size,0))
                   for _ in range(repetitions))
    return MultiEndpointEvidence(tuple(endpoint.signature() for endpoint in endpoints),profile.identity(),
        identity,standalone,combined,tuple(parity),batch_size=batch_size,combined_topk=combined_topk)
