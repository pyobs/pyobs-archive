# specs/

This repo keeps its own implementation plans under `plans/` (like `pyobs-robotic-backend`),
while shared design docs and ADRs live in `pyobs-core`'s `specs/` tree (`specs/design/`,
`specs/plans/`, `specs/adrs/`), each tagged with a `Repos:` line naming every repo it concerns.

Plans:

- [plans/2026-08-20-archive-project-access-control.md](plans/2026-08-20-archive-project-access-control.md) — plan for
  pyobs/pyobs-archive#42: per-project access control for frames (backend project/user mirror +
  endpoint filtering), the archive side of pyobs/pyobs-robotic-backend#79.

Cross-repo:

- `../../pyobs-core/specs/plans/2026-08-19-archive-project-access-control.md` — companion plan
  for the same issue (core/pipeline angle, incl. the mastermind writing the `PROJECT` FITS
  keyword).
- `../../pyobs-core/specs/plans/2026-08-12-shared-auth-keycloak.md` — implemented, closed.
  `pyobs-auth` + Keycloak integration; archive cutover landed as `v2.0.0.dev8`.
- `../../pyobs-core/specs/design/obsnum_fits_header.md` — #738, the `REQNUM`/`OBSNUM` FITS
  keywords used for frame→project association.
- `../../pyobs-robotic-backend/specs/plans/2026-08-20-connect-pyobs-archive.md` — backend-side
  plan (observations → archived frames); its service-token proxy bypasses archive filtering, so
  the backend's own access scoping stays the gate there.
