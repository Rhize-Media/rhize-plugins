# Optional Skylos evidence

Skylos supplies advisory static findings for review. It does not execute your tests, prove a
semantic invariant, approve a release, or authorize deletion. The integration is opt-in; normal
Devflow commands do not install or invoke it. Context Pack integration remains WATCH, with no
runtime changes.

## Local setup and execution

Use an explicitly provisioned, dedicated Python >=3.10 virtual environment with Skylos **4.38.0**.
The reviewed upstream source is `duriantaco/skylos` at
`b9b98894362c971b1aaf6fa3e438a5c328adad3a` (Apache-2.0). Review that source and its dependencies
before installation; provisioning is separate from scanning. The adapter refuses another package
version. It does not authenticate installed package contents from the version string.

Initial support is macOS with `/usr/bin/sandbox-exec` and Git from Apple Command Line Tools.
The worker uses serial scanning (`SKYLOS_JOBS=1`) and the toolchain Git binary directly. A missing runtime, sandbox denial, unsupported
host, timeout, or excessive output returns `unavailable`; there is no unsandboxed fallback.
The report goes to stdout. Save it outside the inspected repository so it does not change Git state:

```bash
python3 "$CLAUDE_PLUGIN_ROOT/scripts/skylos_evidence.py" scan \
  --repo /absolute/repository --base origin/main \
  --python /absolute/dedicated-venv/bin/python > /private/tmp/skylos-report.json
python3 "$CLAUDE_PLUGIN_ROOT/scripts/devflow.py" evidence --json \
  --repo /absolute/repository --base origin/main \
  --skylos-report /private/tmp/skylos-report.json
```

Use the same explicit comparison base as review. `scan` exits 0 for `no_findings`, 1 for `findings`,
and 2 for `incomplete`/`unavailable`. Exit zero means only that selected static checks reported no
findings. Inspect coverage, exclusions, and reasons in every packet. `verify --repo ... --base ...
--report ...` checks reuse without running Skylos; it exits 2 if invalid.

## Boundaries

- The adapter constructs a disposable Git repository from the requested merge base and current
  selected source, including committed branch changes, staged/unstaged changes and untracked files.
  Skylos compares its synthetic HEAD with the current source. The live target is never executed or
  modified.
- Selection is regular `.py`, `.js`, `.jsx`, `.mjs`, `.cjs`, `.ts`, `.tsx` files. Hidden directories,
  dependency/build directories, secret/credential/private-key-shaped names and non-source files are
  excluded. Symlinks fail closed. This heuristic is not a secret detector: source can itself contain
  sensitive literals. Snapshots and reports stay local; treat both as private.
- Limits: 2,000 selected files per tree, 1 MB per file, 32 MB total across both trees, 2 MB combined
  scanner output and 60 seconds scanner time. Git operations have individual 15-second deadlines.
- The scanner receives a sanitized environment with no inherited credentials, contracts or project
  config. Dependency hallucination lookup and contract discovery are both explicitly disabled.
  Networking is denied and checked before importing Skylos. Only disposable scratch is writable;
  source is read-only. System/runtime and Command Line Tools reads are allowed for interpreter/Git operation.
  The root-directory read rule matches only the exact `/` entry, not its descendants.
- Findings preserve only rule ID, relative location and severity. Untrusted finding prose is not
  exposed as a command or instruction. Do not run suggested fixes, tracing, uploads, LLM review,
  cleanups or dependency lookups through this adapter.

## Evidence interpretation

| State | Meaning | Review action |
|---|---|---|
| `findings` | One or more static signals; coverage may still be incomplete | Confirm each against source and the governing invariant |
| `no_findings` | Known coverage completed, with no findings and no unresolved modeled behavior | Continue independent tests and review; no safety claim |
| `incomplete` | Missing coverage, unresolved behavior or incomplete scanner result | Name the gap and use targeted inspection/tests |
| `unavailable` | Input/runtime/sandbox/bounds prevented a usable scan | Name the reason; no inferred clean result |

`accepted: true` means schema, digest and current repository/base/HEAD/source/policy binding agree.
The digest is unsigned and can be recomputed. It is **not an execution attestation**. Do not treat an
externally supplied packet as proof that Skylos ran. Any source, Git state, base or adapter-policy
change requires regeneration. Normal evidence output is unchanged when `--skylos-report` is absent.
An invalid explicitly supplied report produces a warning and an unhealthy evidence packet.

Skylos's behavior model is bounded and Python-focused; it is not a runtime witness. Dynamic dispatch,
framework configuration, excluded manifests and unsupported syntax leave gaps. Its `SKY-A102` test
impact heuristic can be satisfied by an unrelated changed test. A changed assertion is not an
independent oracle. `test-evidence` still reports `execution_unavailable` until its own trusted
execution adapter exists; Skylos never upgrades that verdict.

## Invariant clauses

Use the optional impact-map table to bind each invariant to its owner, structural evidence,
independent check, and unresolved gap. Mark a static hint as advisory rather than claiming the
invariant is verified. Do not generate executable contracts from impact-map prose.

See [the paired fixture evaluation](../../../evals/skylos/README.md) for Arm A (existing deterministic
Devflow evidence) and Arm B (that evidence plus Skylos). This measures a narrow static signal
addition, not agent productivity or full-review superiority. Re-run on adapter or Skylos upgrades;
keep version, fixture hash, arm, outcomes, coverage, misses and runtime in the results.

## Offline schema validation

The runtime verifier reads the bundled scanner schema directly without network access. External
JSON Schema validators checking the full Devflow packet must map the scanner schema URI to its
bundled file in an offline registry; the schema `$id` is an identifier, not a hosted-schema promise.
For example, with `jsonschema` and `referencing` already installed:

```python
import json
from pathlib import Path
from jsonschema import Draft7Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT7

schemas = Path("/absolute/rhize-devflow/schemas")
scanner = json.loads((schemas / "skylos-evidence-v1.schema.json").read_text())
evidence = json.loads((schemas / "devflow-evidence-v1.schema.json").read_text())
registry = Registry().with_resource(
    "https://rhize.media/schemas/skylos-evidence-v1.schema.json",
    Resource.from_contents(scanner, default_specification=DRAFT7),
)
Draft7Validator(evidence, registry=registry).validate(packet)
```

Do not enable remote schema retrieval. These optional validation libraries are not runtime plugin
dependencies; schema validity also does not establish trusted scanner execution.
