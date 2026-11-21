# Verification

- `python3 harness.py check` passed. It ran 2,144 tests across 168 suites
  with 21 skips and validated the repository, OpenSpec and artifact manifest.
- The GitHub dev head matches the audited revision. Rancher Desktop's FAQ
  documents why injecting a Docker host-gateway override is incorrect for
  its reserved host names. The synthetic route fixture reproduces the
  unreachable VM gateway, deduplicates aliases and verifies a replacement
  Windows bridge route on port 9009. A wrong model never receives an
  embedding request.
- The Compose v5 profile matrix rendered CPU, CUDA and Vulkan with default
  and alternate ports. The sidecar manifest has no published embedding port.
  The private route and two explicit external authentication modes were
  exercised through the actual PowerShell scripts with Docker and Windows
  networking boundaries mocked. A wildcard tokenless listener was rejected
  before any request. The pinned PowerShell runtime ran on Linux.
- The cached production Python 3.11 image ran 17 focused tests offline with
  read-only current source mounts, including the actual pinned Java parser.
  The browser fixture exercised encoding form input and preview against the
  existing policy API. Direct SQL fixtures cover multilingual UTF-8 and
  reviewed legacy encodings.
- A synthetic, resumable CPU fixture processed 323 sources, including one
  CP1252 SQL file that initially failed strict decoding. Four parser workers
  were admitted. Repair took 1.385 seconds with one parse and 322 cache hits;
  the warm pass took 1.044 seconds with zero parses and zero new embeddings.
  The fixture used hashing vectors on Linux; those times do not predict a
  physical corporate GPU workload.

The Windows PowerShell fixtures are software checks. The precise corporate
Windows driver, Rancher routing, firewall, first-pull proxy/TLS behavior and
corpus still require acceptance using the matching published image and kit.
Partial index publication is not covered by these results.
