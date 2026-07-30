# OrcaSlicer PR #14989 conformance fixtures

These fixtures validate the permission workflow against synthetic local data.
They are not part of the FilamentHub production plugin.

Safety rules:

- run only with an OrcaSlicer build launched using an isolated `--datadir`;
- the resolved data directory must be below
  `F:\FilamentHub\references\OrcaSlicer_data`;
- use only the marker file `sentinels\declared-read.txt`;
- never copy credentials, personal profiles, tokens, or production data into
  the isolated directory;
- record the exact PR head SHA and artifact evidence for every run;
- run each outcome twice before reporting it upstream.

Expected marker contents:

```text
FILAMENTHUB_ORCA_PERMISSION_FIXTURE_V1
```

Fixtures:

- `fixture_declared_read.py` requests read access during registration and reads
  the marker when its action is executed;
- `fixture_worker_context.py` performs the same marker read in a bounded Python
  worker without a declaration, allowing the host's worker-context behaviour
  to be observed.

Copy one fixture at a time into the isolated OrcaSlicer plugin directory. Do
not install these fixtures into the owner's normal OrcaSlicer profile.
