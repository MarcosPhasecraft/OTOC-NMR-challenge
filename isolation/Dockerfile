# Builds the sandbox image used to run an untrusted submission's
# generate(spec) function. See README.md in this directory and
# TOOLKIT.md item 11 for why this exists and how it's invoked.
#
# The only thing that should change per problem is the pinned pip
# install below -- add exactly what your baselines/solution actually
# import, nothing else. Runtime network access is disabled when the
# container is run (see run_isolated.py), so anything not baked in here
# at build time is simply unavailable to a submission -- there is no way
# for a submission to `pip install` its own dependency.

FROM python:3.12-slim

# --- Per-problem: add what your generate() functions actually import ---
RUN pip install --no-cache-dir numpy==1.26.4
# -------------------------------------------------------------------------

RUN groupadd --gid 65532 runner \
    && useradd --uid 65532 --gid 65532 --no-create-home --shell /usr/sbin/nologin runner

COPY run_generate.py /toolkit/run_generate.py

USER 65532:65532
WORKDIR /toolkit
ENTRYPOINT ["python", "/toolkit/run_generate.py"]
