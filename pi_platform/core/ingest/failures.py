"""Typed candidate failure summary; no source contents or absolute paths."""


class CandidateIndexingError(RuntimeError):
    def __init__(self, categories):
        self.categories = dict(categories)
        self.retryable = all(key == 'transient' for key in categories)
        super().__init__('Incomplete ingestion blocks publication: ' + str(sum(categories.values())) +
                         ' failed sources; review source encoding/configuration and retry Reindex')
