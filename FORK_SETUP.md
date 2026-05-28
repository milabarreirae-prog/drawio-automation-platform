# Fork Setup Guide

## Remotes

Recommended remote layout:

```bash
git remote add origin <your fork url>
git remote add upstream https://github.com/rlespinasse/drawio-desktop-headless.git
```

## Branch Roles

This repository currently uses the following local branch strategy:
- `main`: original local release snapshot
- `backup/local-v0.1.0`: immutable backup of the prototype platform
- `integration/v1.x`: local branch based on `origin/v1.x`
- `port/platform-foundation`: first selective port of the Python automation layer

## Why Not Merge Histories Directly?

The local automation-platform prototype and the remote `v1.x` base do not share a
merge base. A direct unrelated-histories merge would create a noisy and fragile
result because both sides define the repository structure differently.

Instead, integration is being done by selectively porting fork-specific files onto
a branch based on `origin/v1.x`.

## Recommended Workflow

1. Fetch remote updates.
2. Rebase or refresh `integration/v1.x` from `origin/v1.x`.
3. Port or adapt fork-specific features in small validated slices.
4. Run focused tests after each slice.
5. Only merge back to the primary development branch once the integrated branch
   is stable.
