# Supply a public Python 3.11+ base by immutable digest (see README).
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
RUN python -m pip install --no-cache-dir PyYAML==6.0.2 jsonschema==4.23.0
ENV PYTHONDONTWRITEBYTECODE=1 HOME=/tmp
WORKDIR /candidate
USER 65534:65534
