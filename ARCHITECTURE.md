# Architecture

## Overview

This fork layers an automation platform on top of the upstream headless Draw.io runtime.
The upstream base continues to provide the containerized Draw.io Desktop execution model,
while the fork adds an API, async task processing, compliance validation, and enterprise
stencil handling.

## High-Level Flow

1. A client submits Draw.io XML to the FastAPI service.
2. The API validates XML well-formedness, allowed colors, allowed stencils, and
   ArchiMate licensing requirements.
3. Valid requests are queued in Redis through ARQ.
4. A worker resolves stencil dependencies, invokes the Draw.io headless runtime,
   uploads output artifacts, and emits webhook callbacks.
5. Clients query task status through the API or receive asynchronous webhook updates.

## Main Components

### Upstream Runtime Base

The upstream `v1.x` branch remains the base for:
- Draw.io Desktop headless container runtime
- CLI entrypoints and shell wrappers
- Existing Bats-based runtime validation
- Upstream release and publish workflows

### API Layer

Located under `api/`.

Responsibilities:
- Accept rendering requests
- Perform compliance checks before enqueueing work
- Reject invalid diagrams early
- Expose health and task status endpoints

Key technologies:
- FastAPI
- Pydantic / pydantic-settings
- lxml

### Worker Layer

Located under `worker/`.

Responsibilities:
- Resolve stencil libraries and fallbacks
- Execute rendering jobs through the Draw.io runtime
- Upload outputs to S3/MinIO-compatible storage
- Deliver webhook notifications

Key technologies:
- ARQ
- Redis
- boto3

### Compliance Layer

Implemented in `api/linting.py` and related schema/config modules.

Validation includes:
- XML syntax validation
- Color palette restrictions
- Allowed stencil filtering
- ArchiMate license gating

### Stencil Metadata and Tooling

Supporting files live in:
- `stencils/manifest.json`
- `scripts/fetch_stencils.py`
- `scripts/verify_licenses.py`

These files describe supported enterprise stencils and their licensing constraints.

## Branching Strategy Used Here

Because the local platform prototype and `origin/v1.x` did not share history,
integration is being performed by layering fork-specific capabilities onto a branch
based on `origin/v1.x`, instead of performing an unrelated-histories merge.

Current branch roles:
- `backup/local-v0.1.0`: preserves the original local prototype
- `integration/v1.x`: clean branch tracking the remote base
- `port/platform-foundation`: selective port of the Python automation platform

## Validation Status

The Python platform slice ported onto the `v1.x` base currently passes:
- `tests/test_linting.py`
- `tests/test_stencils_loader.py`
- `tests/test_api.py`

This confirms the automation layer can coexist with the upstream runtime base
without forcing a destructive merge strategy.
