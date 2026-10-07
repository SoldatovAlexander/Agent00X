FROM python:3.11.16-slim@sha256:8b29ec24b5f3c929a79b55772b95c93311b7133f1cf7fa0a6141ef621f8e3c57 AS wheel-builder

WORKDIR /build
COPY requirements.lock /build/requirements.lock
COPY wheelhouse/ /build/wheelhouse/
RUN python3 -m pip install \
    --no-index \
    --find-links=/build/wheelhouse \
    --require-hashes \
    --no-deps \
    --only-binary=:all: \
    --target=/opt/target-python \
    -r /build/requirements.lock

FROM python:3.11.16-slim@sha256:8b29ec24b5f3c929a79b55772b95c93311b7133f1cf7fa0a6141ef621f8e3c57 AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/opt/target-python

WORKDIR /workspace
COPY --from=wheel-builder /opt/target-python/ /opt/target-python/
