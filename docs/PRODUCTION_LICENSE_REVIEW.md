# Production dependency policy review

The lock covers 113 exact installed wheel coordinates. No default license policy allowance was expanded. The entries below require review under that policy and are accepted only through the approved exact-closure record; SPDX expressions preserve bundled obligations. This report is evidence for review, not legal approval.

| Coordinate | Recorded SPDX / bundle | Why blocked |
|---|---|---|
| `certifi==2026.10.19` | `MPL-2.0` | Explicit per-coordinate MPL review acceptance required |
| `defusedxml==0.7.1` | `PSF-2.0` | Identifiers/exception or bundled notices are outside current allow list |
| `numpy==2.4.6` | `BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0` | Identifiers/exception or bundled notices are outside current allow list |
| `olefile==0.47` | `BSD-2-Clause AND HPND` | Identifiers/exception or bundled notices are outside current allow list |
| `pandas==3.0.6` | `BSD-3-Clause AND LicenseRef-pandas-bundled-notices` | Identifiers/exception or bundled notices are outside current allow list |
| `pillow==12.3.0` | `MIT-CMU` | Identifiers/exception or bundled notices are outside current allow list |
| `pypdfium2==5.14.0` | `BSD-3-Clause AND Apache-2.0 AND MIT AND BSD-2-Clause AND FTL AND Unicode-3.0 AND IJG AND Libpng-2.0 AND (Apache-2.0 WITH LLVM-exception) AND Zlib AND LicenseRef-pypdfium2-bundled-notices` | Identifiers/exception or bundled notices are outside current allow list |
| `regex==2026.9.29` | `Apache-2.0 AND CNRI-Python` | Identifiers/exception or bundled notices are outside current allow list |
| `scipy==1.17.1` | `BSD-3-Clause AND BSD-3-Clause-Open-MPI AND (GPL-3.0-or-later WITH GCC-exception-3.1) AND LGPL-2.1-or-later` | Identifiers/exception or bundled notices are outside current allow list |
| `torch==2.14.1+cpu` | `Apache-2.0 AND Apache-2.0 WITH LLVM-exception AND BSD-2-Clause AND BSD-3-Clause AND BSL-1.0 AND MIT` | Identifiers/exception or bundled notices are outside current allow list |
| `tqdm==4.70.1` | `MPL-2.0 AND MIT` | Explicit per-coordinate MPL review acceptance required |
| `typing-extensions==4.16.0` | `PSF-2.0` | Identifiers/exception or bundled notices are outside current allow list |

`scipy` ships actual `libgfortran` and `libquadmath` binaries; its bundled license document identifies the GCC runtime exception and LGPL terms. `tqdm` uses MPL and MIT for different contributions, so replacing AND with OR would lose obligations. `olefile` retains the legacy PIL license in addition to its BSD terms.

The pandas and PDFium LicenseRefs identify retained bundled notices that require review rather than an inferred headline license. All reviewed installed license texts and hashes are retained in [production-license-evidence.json](../distribution/licenses/production-license-evidence.json). Per-wheel metadata hashes, exact lock hash, upstream URLs and audited file hashes are in [production-dependency-inventory.json](../distribution/licenses/production-dependency-inventory.json).

Reproduce the policy result without installing dependencies:

```bash
python3 -m pi_platform.cli license-gate --inventory distribution/licenses/production-dependency-inventory.json --production-lock requirements-production-linux-x86_64.txt
```

The command without a review record fails intentionally on the listed coordinates. Production builds and publication supply the approved scoped record shown below and pass for this exact closure. Generic core license-gate success proves neither this closure nor production readiness.

## Local source installation

The [source installation](PRODUCTION_INSTALL.md) downloads the locked dependency
wheels directly from their publishers into a local virtual environment. Those
packages retain their own licenses and installed `dist-info` notices. Local
startup runs the production capability checks; it does not automatically run
the combined-distribution license gate. You can install and run from source
while the default policy still requires the scoped review record for production. The
explicit production license command above continues to report the same failures.

## Combined production container

Building the `production` Containerfile target combines the dependency wheels
into a redistributable artifact. Its build runs the exact-closure license gate
and creates SBOM/NOTICE only after that gate passes. The approved exact-closure review resolves these coordinates for this target;
changed or unreviewed coordinates still block production image publication. The source installation commands do not represent approval to
redistribute a combined image or waive any dependency's terms.

## Historical proposed review record — not used by builds

The [concrete unapproved proposal](production-license-review-proposal.json) binds
all twelve blocked coordinates to the current exact lock, inventory and license
evidence hashes. It contains pending decisions and is not consumed by the gate.

A reviewer can resolve the recorded terms for this particular dependency closure
without expanding the global default allow list. The following is a proposed
record shape for that review, not a supported bypass flag or an approved policy:

```json
{
  "status": "proposed-unapproved",
  "artifact": "production-linux-x86_64",
  "lock_sha256": "copy the current requirements lock SHA-256",
  "coordinates": [
    {
      "name": "certifi",
      "version": "2026.10.19",
      "license_expression": "MPL-2.0",
      "decision": "pending",
      "evidence": "production-dependency-inventory.json and retained license texts",
      "obligations": "record the reviewed notices and redistribution obligations"
    }
  ]
}
```

Each of the blocked coordinates requires its own decision, bound to its exact
version, license evidence and lock hash. A new version, changed artifact or
changed license evidence invalidates that coordinate's decision. Keep copyright
and license notices with the image and ensure accepted entries appear in both
SBOM and NOTICE. The GCC runtime exception and LGPL terms require review of the
actual bundled SciPy libraries; a blanket statement about GPL is insufficient.
The operator explicitly accepted the exact recorded closure on 2026-10-22.

## Executable exact-closure review

`distribution/licenses/production-license-review.json` is now consumed by the
production Containerfile and publishing workflows via `--license-review`, with
`--license-evidence` and `--production-lock`. It is approved for the exact recorded closure.
The gate requires `status: approved`, operator attribution/date, an accepted
coordinate decision and obligations, plus matching SHA-256 hashes of the lock,
inventory and retained evidence. A changed input invalidates the review. It does
not expand the default policy. Accepted exact coordinates appear in NOTICE and
SBOM; installed wheel license files remain in the image.

A proposed record, missing attribution, pending coordinate, altered evidence or
unreviewed dependency remains build-blocking. The acceptance covers this concrete record, not unrestricted future dependencies.
