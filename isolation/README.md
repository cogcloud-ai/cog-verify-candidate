# Isolated verification

Docker is an explicit host prerequisite. No provider, credentials, sibling
workspace, host home directory, Docker socket, or network is mounted into the
execution container. This policy is for pure Python Cogs using stdlib, PyYAML
and jsonschema. Other task executables and dependency sets are refused.

Build a local image from an immutable public base:

```sh
docker pull python:3.11-slim
# Copy its RepoDigest from this command; no secret output is needed.
docker image inspect python:3.11-slim --format '{{index .RepoDigests 0}}'
docker build --build-arg BASE_IMAGE=python@sha256:BASE_DIGEST -t cog-verification -f isolation/Dockerfile .
docker image inspect cog-verification --format '{{.Id}}'
```

Supply the resulting `sha256:...` image ID as `execution_policy.image`:

```json
{"mode":"docker","image":"sha256:YOUR_64_HEX_DIGEST","timeout_seconds":60,"output_bytes":1048576}
```

Set this object as the verifier's optional `execution_policy` input. The builder
also forwards it. A missing image/daemon stops verification; Docker mode never
falls back to local execution. Images are inspected and executed with
`--pull never`. The policy receipt retains resolved image ID, OS, architecture,
limits and policy digest alongside each operation's bounded stdout/stderr,
exit status and timeout/output-limit outcome.

The container has no network, read-only filesystem and candidate/input mounts,
a 64 MiB temporary directory, no Linux capabilities, no new privileges,
UID/GID 65534, one CPU, 256 MiB memory (including swap), and 64 processes.
Both declared tests and planned/reference invocations use the same policy.
The host supervisor kills timed-out process groups and removes the container.
Post-execution fingerprints still refuse a changed candidate/reference.
See [Docker's run options](https://docs.docker.com/reference/cli/docker/container/run/).
This relies on the configured Docker daemon and image; it does not attest their
integrity or provide protection against a compromised host/kernel.

Omitting the policy keeps the explicitly labelled `trusted-local` compatibility
mode, with time/output bounds but ambient host filesystem/network/credentials.
It is suitable for reviewed local fixtures. A local-mode receipt never claims
resource or filesystem isolation. Failed tests and bounded-case failures are
observations for independent review, and never grant acceptance.

Run the real container checks after building:

```sh
COG_VERIFY_ISOLATION_IMAGE=sha256:IMAGE_ID pixi run test
```

Linux CI builds a digest-pinned base and executes these checks. Without the
variable, only the actual Docker checks skip; process-limit tests still run.

Trusted-local descendants that start a new session can escape process-group
termination; use Docker for confinement. With no explicit timeout the original
operation deadline applies (600 seconds for declared tests, 240 for cases). An
explicit policy caps that deadline. Full bounded output is saved once in the
observation file; per-criterion test evidence refers to that record. Container
cleanup failures are retained in the observation rather than hiding its outcome.
