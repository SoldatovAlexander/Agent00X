FROM python:3.11.16-slim@sha256:e41613d42d4891e4930f79523f93f81bbc7632584ec65e36ab055f41a800b41e AS wheel-builder

WORKDIR /build
COPY requirements.lock /build/requirements.lock
COPY wheelhouse/ /build/wheelhouse/
RUN python3 -m pip install \
    --no-index \
    --find-links=/build/wheelhouse \
    --require-hashes \
    --no-deps \
    --no-compile \
    --only-binary=:all: \
    --target=/opt/target-python \
    -r /build/requirements.lock \
    && find /opt -exec touch -h -d '@0' {} +

FROM python:3.11.16-slim@sha256:e41613d42d4891e4930f79523f93f81bbc7632584ec65e36ab055f41a800b41e AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/opt/target-python

WORKDIR /workspace
RUN --mount=type=bind,from=wheel-builder,source=/opt,target=/tmp/opt,ro \
    mkdir -p /opt \
    && cp -a /tmp/opt/target-python /opt/target-python \
    && find /opt -exec touch -h -d '@0' {} +
