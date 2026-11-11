# Isolated verification

Docker is an explicit host prerequisite: use Docker Engine 29.9.2 or newer, or
Docker Desktop 4.96.2 or newer. Earlier versions may still accept the
compromised eMudhra intermediate CAs when pulling images, depending on the
host's certificate store. No provider, credentials, sibling workspace, host home
directory, Docker socket, or network is mounted into the execution container.
This policy is for pure Python Cogs using stdlib, PyYAML and jsonschema. Other
task executables and dependency sets are refused.

Build a local image from an immutable public base running Python 3.11 through
3.14, at or above that line's first release that rejects the compromised
eMudhra intermediate CAs: 3.11.18, 3.12.16, 3.13.18 or 3.14.10. Official
`python` images report their release as `PYTHON_VERSION` in the environment
printed below; for other bases, run `python --version` in the image:

```sh
docker pull python:3.11-slim
# Copy its RepoDigest from this command; no secret output is needed.
docker image inspect python:3.11-slim --format '{{index .RepoDigests 0}}'
docker image inspect python:3.11-slim --format '{{json .Config.Env}}'
docker build --build-arg BASE_IMAGE=python@sha256:BASE_DIGEST -t cog-verification -f isolation/Dockerfile .
docker image inspect cog-verification --format '{{.Id}}'
```

The image installs PyYAML, jsonschema and their dependencies from
[`requirements.txt`](requirements.txt), with every download checked against its
pinned hash. A substituted package fails the build, whatever certificates the
base image trusts. Only wheels are installed, since building a source
distribution would fetch its build dependencies without hash checks. To change a
version, edit [`requirements.in`](requirements.in) and regenerate the lock with
the `uv` command in the header of `requirements.txt`, using uv 0.13.5 or newer
and keeping `--universal` so it covers every platform and Python version. The
hashes come from PyPI over TLS, so an older uv could record hashes of
substituted packages, which every later build would then accept. CI regenerates
the lock and fails if it differs from the committed file.

Rebuild any image built before this hash pinning from a base older than the
releases listed above (check with the `PYTHON_VERSION` command above, using your
image ID). Its packages were downloaded over a connection that could have been
intercepted using the compromised eMudhra intermediate keys.

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

Linux CI resolves the base tag to a digest for each build (the tag may change
between builds), builds from that digest, and executes these checks. Without the
variable, only the actual Docker checks skip; process-limit tests still run.

Trusted-local descendants that start a new session can escape process-group
termination; use Docker for confinement. With no explicit timeout the original
operation deadline applies (600 seconds for declared tests, 240 for cases). An
explicit policy caps that deadline. Bounded output is retained in execution observations, check records and the
returned test payload; per-criterion test evidence refers to that record and includes at most 4,096
characters from each stdout/stderr tail for independent repair review, repeated
for each linked criterion. Truncation flags and retained character counts identify
these excerpts; they describe captured output, which may itself be bounded. Container
cleanup failures are retained in the observation rather than hiding its outcome.
