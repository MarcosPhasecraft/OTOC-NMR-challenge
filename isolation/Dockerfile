# Builds the sandbox image used to run an untrusted submission's
# generate(spec) function. See README.md in this directory and
# TOOLKIT.md item 11 for why this exists and how it's invoked.
#
# Per-problem pins: exactly what baselines/ and solution/ may import.
# Runtime network access is disabled when the container is run, so a
# submission cannot install anything itself -- if it isn't here, it
# isn't available.

FROM python:3.13-slim

# --- Per-problem: what generate() functions may import --------------------
# harness/ is mounted read-only at /harness and is on PYTHONPATH; it imports
# numpy, cirq and otoc-core's circuit builder. otoc-core is installed from a
# wheel built with `pip wheel --no-deps -w isolation/wheels /path/to/otoc-core`
# (its own dependency list needs Phasecraft's private index; see README.md).
# Escape hatch for build hosts behind a TLS-intercepting proxy: pass
#   --build-arg PIP_TRUSTED_HOST="pypi.org files.pythonhosted.org"
# Leave it empty (the default) everywhere else so pip verifies certificates.
ARG PIP_TRUSTED_HOST=
ENV PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}
COPY wheels/ /wheels/
RUN pip install --no-cache-dir numpy==2.5.3 scipy==1.18.1 openfermion==1.8.1 cirq-core==1.7.0 \
    && pip install --no-cache-dir --no-deps /wheels/otoc_core-*.whl \
    && rm -rf /wheels
# -------------------------------------------------------------------------

RUN groupadd --gid 65532 runner \
    && useradd --uid 65532 --gid 65532 --no-create-home --shell /usr/sbin/nologin runner

COPY run_generate.py /toolkit/run_generate.py

USER 65532:65532
WORKDIR /toolkit
ENTRYPOINT ["python", "/toolkit/run_generate.py"]
