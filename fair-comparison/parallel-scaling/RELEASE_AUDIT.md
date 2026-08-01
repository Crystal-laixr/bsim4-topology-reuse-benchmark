# Release Audit

- Matrix gate: passed for 872 valid JSON records.
- Records with failed worker shards: 226; preserved on the server under
  `data/raw/invalid/` and excluded from release analysis.
- License preflight archives: preserved on the server but excluded from the
  public release.
- Files larger than 100 MB: none in the release payload.
- HSPICE binaries, license files, daemon logs, credentials, and private model
  assets: excluded.
- The complete solver-only DC curves remain; end-to-end and transient results
  use the reduced sampled scope documented in `REDUCED_SCOPE.md`.
