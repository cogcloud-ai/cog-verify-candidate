---
type: cog [0.1]
name: cog-verify-candidate
description: "Collect candidate-bound declared test and case observations."
version: "0.1.0"
license: Apache-2.0
publisher: OpenTeams
manifest: pixi.toml
manifest_schema: openteams/cog-manifest [0.1]
---

# cog-verify-candidate

This deterministic supporting Cog executes a pure code candidate's declared
test task and evaluator-planned usage cases. It returns a complete review request
with source-bound execution evidence. It never makes a semantic acceptance or
publication decision. This is independently reusable verification work with its
own identity and package-stability checks.

Input contains the materialization result, exact author request/envelope,
checked evaluator plan, and the caller's test_criterion_ids. Package and source
fingerprints are checked before execution and after the tests/cases. Each linked
declared-test observation states its limited scope; the evaluator must assess
actual coverage. A failing test suite remains failed evidence and proceeds to
review. An invalid plan or changed package refuses instead of creating evidence.

An optional pinned pure-code reference can receive the candidate's authored
named-bundle fixtures. The worker preserves both envelopes, compares normalized
payload/problem results, and separately records full-problem equality. These
are observations for the designated criterion, not semantic acceptance. Both
package fingerprints must remain unchanged; the reference is never modified.

There is no automatic install, model binding, or arbitrary command argument.
Only declared operations execute. Workbench uses an installed candidate Python
when present, otherwise this worker's installed Python (stdlib/pyyaml/jsonschema).
Both execution environments are trusted local code execution, not sandboxes.
The test record is an observation, not proof that generated tests are adequate.

Normally this worker receives op-cog-builder's verify-step request. The supplied
hand-written sample requires first running cog-build-candidate's sample. It
points at that fixed fixture package and uses its actual source/package digests;
it is a portable seam example, not live model evidence. Then invoke
`pixi run run -- --bundle examples/sample-bundle.json`. If Smith templates change,
regenerate the example artifacts and fingerprints rather than bypassing checks.
See ../op-cog-builder/README.md for the real composition.

## Local host contract

This first implementation requires sibling cog-workbench, cog-author,
cog-build-evaluator and cog-smith installations. It uses the declared
`openteams/local-builder-host [0.1-draft]` extension and Workbench's local
package operations API; it does not import another Cog's task implementation.
The host path is fixed relative to this checkout, never supplied by task input.
No cloud registry portability or constrained execution environment is claimed.

Local run artifacts and declared subprocess operations are the work. There are
no protected-service reaches or external grants in this slice. Generated code
runs with the owner's ambient authority; the caller must admit that execution.
No model calls, publication, reference edits, or free-form shell commands are
supported. This Cog does not coordinate the build lifecycle; the Op does.

Install with `pixi install`; run `pixi run test`. Results use envelope v1 with
code identity, structured problems, and no model binding. Gates belong to the
Op. Only src/task_logic.py is Cog-owned; shared machinery remains Smith-owned.
