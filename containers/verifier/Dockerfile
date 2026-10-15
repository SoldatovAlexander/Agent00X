FROM python:3.11.16-slim@sha256:174bec68e0451bffabbb08c7d5d21c6b253f772d81d52b9558af97bb3159b761

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/opt/agent00x/src \
    TMPDIR=/work

WORKDIR /work
COPY requirements.lock /opt/agent00x/target-runtime-requirements.lock
COPY target-python/ /usr/local/lib/python3.11/site-packages/
COPY src/app_contracts/__init__.py \
     src/app_contracts/brainbooster_target_profile.py \
     src/app_contracts/digests.py \
     src/app_contracts/executor.py \
     src/app_contracts/observer_runtime.py \
     src/app_contracts/observation_store.py \
     src/app_contracts/pinned_snapshot.py \
     src/app_contracts/repository_process.py \
     src/app_contracts/sandbox.py \
     src/app_contracts/validator.py \
     src/app_contracts/verifier_process.py \
     src/app_contracts/verifier_container_entrypoint.py \
     /opt/agent00x/src/app_contracts/
COPY schemas/checkpoint.schema.json schemas/observation-event.schema.json \
     /opt/agent00x/schemas/

USER 65532:65532
ENTRYPOINT ["python3", "-m", "app_contracts.verifier_container_entrypoint"]
