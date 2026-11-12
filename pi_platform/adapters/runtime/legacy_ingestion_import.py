"""Bounded standard-library reader for the legacy cache's object sections."""
import json


class LegacyCacheReader:
    def __init__(self, stream):
        self.stream = stream
        self.buffer = ''
        self.end = False
        self.decoder = json.JSONDecoder()

    def _more(self):
        part = self.stream.read(65536)
        self.end = not part
        self.buffer += part

    def _space(self):
        self.buffer = self.buffer.lstrip()
        while not self.buffer and not self.end:
            self._more()
            self.buffer = self.buffer.lstrip()

    def peek(self):
        self._space()
        return self.buffer[:1]

    def consume(self, character):
        self._space()
        if not self.buffer.startswith(character):
            raise ValueError('Malformed legacy ingestion cache structure')
        self.buffer = self.buffer[1:]

    def value(self):
        self._space()
        while True:
            try:
                value, count = self.decoder.raw_decode(self.buffer)
                # A number can end at a buffer boundary, unlike objects/strings.
                if count == len(self.buffer) and not self.end:
                    self._more()
                    continue
                self.buffer = self.buffer[count:]
                return value
            except json.JSONDecodeError:
                if self.end:
                    raise ValueError('Malformed legacy ingestion cache entry') from None
                if len(self.buffer) > 64 * 1024 * 1024:
                    raise ValueError('Legacy cache entry exceeds bounded migration limit (64 MiB)')
                self._more()

    def keys(self):
        self.consume('{')
        first = True
        while self.peek() != '}':
            if not first:
                self.consume(',')
            first = False
            key = self.value()
            if not isinstance(key, str):
                raise ValueError('Legacy cache object key must be a string')
            self.consume(':')
            yield key
        self.consume('}')


def legacy_entries(path):
    """Yield one record/source at a time, independent of top-level key order."""
    with path.open(encoding='utf-8') as stream:
        reader = LegacyCacheReader(stream)
        for section in reader.keys():
            if reader.peek() == '{':
                for key in reader.keys():
                    value = reader.value()
                    if section in ('records', 'sources'):
                        yield section, key, value
            else:
                reader.value()
        if reader.peek():
            raise ValueError('Trailing data in legacy ingestion cache')
