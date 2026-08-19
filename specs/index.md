# specs/

This repo has no `specs/` structure of its own. Design docs, implementation plans, and ADRs
that concern `pyobs-archive` — including ones actually implemented here — live in `pyobs-core`'s
`specs/` tree instead (`specs/design/`, `specs/plans/`, `specs/adrs/`), each tagged with a
`Repos:` line naming every repo it concerns. See `pyobs-core/CLAUDE.md`'s "Cross-repo docs"
section.

Relevant so far:

- `pyobs-core/specs/plans/2026-08-12-shared-auth-keycloak.md` — implemented, closed. `pyobs-auth`
  + Keycloak integration; archive cutover landed as `v2.0.0.dev8`.
- `pyobs-core/specs/plans/2026-08-19-archive-project-access-control.md` — planned. Show only
  images the logged-in user has access to, keyed on projects from `pyobs-robotic-backend`
  (tracks pyobs/pyobs-archive#42, depends on pyobs/pyobs-robotic-backend#79).
