# Supply a public, patched Python 3.11-3.14 base by immutable digest (see
# README). Build from the repository root, so isolation/ is in the context.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
# Every package is pinned by hash, so a substituted download fails the build
# whatever certificates the base image trusts. Wheels only: building an sdist
# would fetch its build dependencies without hash checks.
COPY isolation/requirements.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir --require-hashes --only-binary=:all: \
    -r /tmp/requirements.txt
ENV PYTHONDONTWRITEBYTECODE=1 HOME=/tmp
WORKDIR /candidate
USER 65534:65534
