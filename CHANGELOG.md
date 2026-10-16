# Changelog

## Unreleased — Wenjin open-source evolution candidate (2026-10-16)

### Added

- Versioned Open API V1 capability manifest, provider contract snapshot and standard-library example.
- Project-scoped collaboration membership, artifact versions, annotations, review tasks, pagination and revocable redacted sharing.
- Default-off collaboration research workspace for members and research artifact metadata.
- WISE proposal/approval/revocation boundary and shared research prompt guardrails.
- Private knowledge-package manifest gate with hash, approval, bounded card shape, language, field and method metadata checks.
- Public metadata-only register for bilingual knowledge candidates; candidate materials remain `needs_review`.

### Security and privacy

- Provider credentials remain server-side; client requests cannot submit provider keys or arbitrary upstream URLs.
- Refresh tokens are stored as server-side digests and delivered through HttpOnly cookies; access tokens remain memory-only in the browser.
- WebSocket authentication uses the `bearer` subprotocol and does not accept URL tokens.
- Public source excludes private training materials, raw research data, logs, deployment secrets and unconfirmed third-party content.

### Known release-candidate limits

- This branch is not a production SaaS security or ethics certification.
- Frontend lint, dependency/license audit, PostgreSQL/Redis integration and Docker smoke require a CI or equipped environment; Docker was unavailable in the local verification environment.
- API token lifecycle, webhooks, public streaming, full typed SDK, batch review and executable third-party extensions are out of scope for this candidate.
- Knowledge candidates require project-owner review and rights clearance before any private deployment may mark them `approved`.
