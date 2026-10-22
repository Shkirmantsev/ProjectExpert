#!/usr/bin/env python3
"""Record exact installed wheel license evidence; this does not approve licenses."""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.metadata
import json
import re
from pathlib import Path

CLASSIFIERS = {
    "License :: OSI Approved :: MIT License": "MIT",
    "License :: OSI Approved :: Apache Software License": "Apache-2.0",
    "License :: OSI Approved :: ISC License (ISCL)": "ISC",
    "License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
}
LEGACY = {
    "MIT": "MIT", "MIT License": "MIT", "Apache": "Apache-2.0",
    "Apache-2.0": "Apache-2.0", "Apache 2.0": "Apache-2.0",
    "Apache 2.0 License": "Apache-2.0", "BSD-2-Clause": "BSD-2-Clause",
    "BSD-3-Clause": "BSD-3-Clause", "ISC License": "ISC", "MPL-2.0": "MPL-2.0",
}


# These exact installed versions were checked against the shipped license
# texts. Bundled terms are retained instead of reducing the wheel to its
# upstream project's headline license. LicenseRefs remain policy-blocking.
AUDITED = {
    ("defusedxml", "0.7.1"): "PSF-2.0",
    ("jinja2", "3.1.6"): "BSD-3-Clause",
    ("mpmath", "1.3.0"): "BSD-3-Clause",
    ("olefile", "0.47"): "BSD-2-Clause AND HPND",
    ("omegaconf", "2.4.0"): "BSD-3-Clause",
    ("protobuf", "7.36.2"): "BSD-3-Clause",
    ("pandas", "3.0.6"): "BSD-3-Clause AND LicenseRef-pandas-bundled-notices",
    ("python-dateutil", "2.9.0.post0"): "BSD-3-Clause",
    ("scipy", "1.17.1"): "BSD-3-Clause AND BSD-3-Clause-Open-MPI AND (GPL-3.0-or-later WITH GCC-exception-3.1) AND LGPL-2.1-or-later",
    ("sympy", "1.14.0"): "BSD-3-Clause AND MIT",
    ("torchvision", "0.29.1+cpu"): "BSD-3-Clause",
    ("tqdm", "4.70.1"): "MPL-2.0 AND MIT",
    ("pypdfium2", "5.14.0"): "BSD-3-Clause AND Apache-2.0 AND MIT AND BSD-2-Clause AND FTL AND Unicode-3.0 AND IJG AND Libpng-2.0 AND (Apache-2.0 WITH LLVM-exception) AND Zlib AND LicenseRef-pypdfium2-bundled-notices",
}


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def generate(lock: Path, retained_texts: dict | None = None) -> dict:
    requirements = {}
    for line in lock.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([A-Za-z0-9_.-]+)==([^\s\\]+)", line)
        if match:
            requirements[normalize(match[1])] = match[2]
    if not requirements:
        raise ValueError("Production lock has no exact requirements")
    installed = {normalize(d.metadata["Name"]): d for d in importlib.metadata.distributions()}
    records = []
    for name, version in sorted(requirements.items()):
        distribution = installed[name]
        metadata = distribution.metadata
        if distribution.version != version:
            raise ValueError(f"Installed {name} {distribution.version} differs from locked {version}")
        expression = metadata.get("License-Expression")
        classifiers = metadata.get_all("Classifier", [])
        license_classifiers = [c for c in classifiers if c.startswith("License ::")]
        legacy = (metadata.get("License") or "").strip()
        mapped = {CLASSIFIERS[c] for c in license_classifiers if c in CLASSIFIERS}
        if expression:
            spdx, evidence = expression, "License-Expression"
        elif legacy in LEGACY:
            spdx, evidence = LEGACY[legacy], "exact legacy License field"
        elif len(mapped) == 1 and len(license_classifiers) == 1:
            spdx, evidence = mapped.pop(), "unambiguous license classifier"
        else:
            spdx, evidence = "NOASSERTION", "ambiguous or missing wheel license metadata; review required"
        audited_files = []
        if (name, version) in AUDITED:
            spdx, evidence = AUDITED[(name, version)], "audited installed license texts; bundled obligations retained"
            for file in distribution.files or []:
                if "dist-info/" in str(file) and any(word in str(file).lower() for word in ("license", "licence", "copying")):
                    path = distribution.locate_file(file)
                    content = path.read_bytes()
                    audited_files.append({"path": str(file), "sha256": hashlib.sha256(content).hexdigest()})
                    if retained_texts is not None:
                        retained_texts[f"{name}=={version}/{file}"] = {"sha256": hashlib.sha256(content).hexdigest(), "bytes_base64": base64.b64encode(content).decode("ascii"), "text": content.decode("utf-8", errors="replace")}
        project_urls = metadata.get_all("Project-URL", [])
        records.append({
            "name": name, "version": version, "spdx": spdx, "scope": "production",
            "source": f"https://pypi.org/project/{name}/{version}/",
            "evidence": {
                "kind": evidence,
                "upstream_urls": project_urls,
                "audited_license_files": audited_files,
                "metadata_sha256": hashlib.sha256((distribution.read_text("METADATA") or "").encode()).hexdigest(),
                "wheel_sha256": hashlib.sha256((distribution.read_text("WHEEL") or "").encode()).hexdigest(),
                "license_expression": expression,
                "license_classifiers": license_classifiers,
                "license_files": metadata.get_all("License-File", []),
                "lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
            },
        })
    return {"schema_version": "1.0", "notes": "Exact installed wheel metadata evidence. Unknown licenses and policy-required reviews remain blocking; metadata extraction is not license approval.", "dependencies": records}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, default=Path("requirements-production-linux-x86_64.txt"))
    parser.add_argument("--output", type=Path, default=Path("distribution/licenses/production-dependency-inventory.json"))
    args = parser.parse_args()
    retained_texts = {}
    payload = generate(args.lock, retained_texts)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (args.output.parent / "production-license-evidence.json").write_text(json.dumps(retained_texts, indent=2) + "\n", encoding="utf-8")
    print(f"Recorded {len(payload['dependencies'])} exact installed coordinates; license policy acceptance is separate.")


if __name__ == "__main__":
    main()
