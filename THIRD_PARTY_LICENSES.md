# Third-Party Licenses

This file summarizes the stencil libraries and related third-party terms used by
this forked automation platform.

## Stencil Summary

| Stencil | Provider | License / Terms | Notes |
| --- | --- | --- | --- |
| `aws4` | Amazon Web Services | Proprietary terms with attribution expectations | Intended for architecture diagrams |
| `gcp2` | Google | CC BY 4.0 | Attribution required |
| `azure` | Microsoft | Proprietary icon terms | Attribution may be required |
| `archimate3` | The Open Group | Commercial licensing required for some use cases | Gated by `ARCHIMATE_LICENSE_KEY` |
| `c4` | Simon Brown / structurizr | CC BY 4.0 | Attribution required |
| `cisco` | Cisco | Proprietary icon terms | Attribution may be required |
| `oci` | Oracle | Proprietary icon terms | Attribution may be required |
| `leanix` | LeanIX / SAP | Proprietary | Marked unavailable by default |

## Operational Policy

The fork does not assume that all stencils are freely redistributable.
Instead it uses policy-aware handling:
- allowed stencils are explicitly enumerated
- ArchiMate use can be blocked without a configured license key
- unavailable stencils can be rejected or downgraded depending on policy

## Source of Truth

Detailed machine-readable metadata lives in `stencils/manifest.json` and is
validated by `scripts/verify_licenses.py`.
