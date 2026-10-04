"""Read public JVM signatures, hierarchy, annotations and module exports (no decompilation)."""

import struct


class Reader:
    def __init__(self, data):
        self.data = data
        self.pos = 0

    def take(self, n):
        value = self.data[self.pos : self.pos + n]
        if len(value) != n:
            raise ValueError("truncated class file")
        self.pos += n
        return value

    def u1(self):
        return self.take(1)[0]

    def u2(self):
        return struct.unpack(">H", self.take(2))[0]

    def u4(self):
        return struct.unpack(">I", self.take(4))[0]


def parse_class(data):
    r = Reader(data)
    if r.u4() != 0xCAFEBABE:
        raise ValueError("invalid class file magic")
    r.u2()
    major = r.u2()
    size = r.u2()
    cp = [None] * size
    i = 1
    while i < size:
        tag = r.u1()
        if tag == 1:
            cp[i] = r.take(r.u2()).decode("utf-8", errors="replace")
        elif tag in (7, 8, 16, 19, 20):
            cp[i] = (tag, r.u2())
        elif tag in (3, 4):
            r.take(4)
        elif tag in (5, 6):
            r.take(8)
            i += 1
        elif tag in (9, 10, 11, 12, 17, 18):
            r.take(4)
        elif tag == 15:
            r.take(3)
        else:
            raise ValueError(f"unsupported constant-pool tag {tag}")
        i += 1

    def string(index):
        if index == 0:
            return ""
        item = cp[index]
        return string(item[1]) if isinstance(item, tuple) else str(item)

    def annotations(payload):
        ar = Reader(payload)

        def element():
            tag = chr(ar.u1())
            if tag in "BCDFIJSZs":
                ar.u2()
            elif tag == "e":
                ar.u2()
                ar.u2()
            elif tag == "c":
                ar.u2()
            elif tag == "@":
                annotation()
            elif tag == "[":
                for _ in range(ar.u2()):
                    element()
            else:
                raise ValueError("invalid annotation value")

        def annotation():
            name = string(ar.u2())
            for _ in range(ar.u2()):
                ar.u2()
                element()
            return name

        return [annotation() for _ in range(ar.u2())]

    def attributes(reader):
        attrs = {}
        for _ in range(reader.u2()):
            name = string(reader.u2())
            payload = reader.take(reader.u4())
            if name == "Signature":
                attrs["signature"] = string(Reader(payload).u2())
            elif name == "RuntimeVisibleAnnotations":
                attrs["annotations"] = annotations(payload)
            elif name == "Module":
                mr = Reader(payload)
                attrs["moduleName"] = string(mr.u2())
                mr.u2()
                mr.u2()
                requires = []
                for _ in range(mr.u2()):
                    requires.append(string(mr.u2()))
                    mr.u2()
                    mr.u2()
                exports = []
                for _ in range(mr.u2()):
                    exports.append(string(mr.u2()))
                    mr.u2()
                    for _ in range(mr.u2()):
                        mr.u2()
                attrs["requires"] = requires
                attrs["exports"] = exports
        return attrs

    access = r.u2()
    name = string(r.u2())
    superclass = string(r.u2())
    interfaces = [string(r.u2()) for _ in range(r.u2())]

    def members():
        result = []
        for _ in range(r.u2()):
            flags = r.u2()
            label = string(r.u2())
            descriptor = string(r.u2())
            attrs = attributes(r)
            if flags & 1:
                result.append(
                    {
                        "name": label,
                        "descriptor": descriptor,
                        "modifiers": flags,
                        **attrs,
                    }
                )
        return result

    fields = members()
    methods = members()
    attrs = attributes(r)
    return {
        "name": name,
        "superclass": superclass,
        "interfaces": interfaces,
        "access": access,
        "major": major,
        "fields": fields,
        "methods": methods,
        **attrs,
    }
