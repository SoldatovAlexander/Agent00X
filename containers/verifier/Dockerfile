FROM python:3.11.16-slim@sha256:8b29ec24b5f3c929a79b55772b95c93311b7133f1cf7fa0a6141ef621f8e3c57

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/opt/agent00x/src \
    TMPDIR=/work

WORKDIR /work
COPY requirements.lock /opt/agent00x/target-runtime-requirements.lock
COPY target-python/ /usr/local/lib/python3.11/site-packages/
COPY src/app_contracts/__init__.py \
     src/app_contracts/digests.py \
     src/app_contracts/executor.py \
     src/app_contracts/pinned_snapshot.py \
     src/app_contracts/repository_process.py \
     src/app_contracts/sandbox.py \
     src/app_contracts/validator.py \
     src/app_contracts/verifier_process.py \
     src/app_contracts/verifier_container_entrypoint.py \
     /opt/agent00x/src/app_contracts/

USER 65532:65532
ENTRYPOINT ["python3", "-m", "app_contracts.verifier_container_entrypoint"]
