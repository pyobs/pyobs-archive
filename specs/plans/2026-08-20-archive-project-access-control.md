# Plan: Project-based access control for pyobs-archive

Tracks pyobs/pyobs-archive#42. Depends on pyobs/pyobs-portal#79 (per-project `public`
flag; closed, already implemented) and on a pyobs-core mastermind change to write the `PROJECT`
FITS keyword (alongside `REQNUM`/`OBSNUM`; see §1 — until it lands, the `REQNUM` fallback
carries the association).
Repos: pyobs-archive, pyobs-portal, pyobs-core.

Status: done (sections 1-5, 7 shipped in #45, #46; section 6 backfill deliberately skipped —
see §6; section 8 frontend column skipped as optional)

## Problem

The archive serves every archived frame to any authenticated user: `frames_view`,
`aggregate_view`, `zip_view` and the per-frame endpoints (`frame_view`, `download_view`,
`preview_view`, `headers_view`, `catalog_view`, `related_view`) are all `IsAuthenticated` with
no per-user filtering (`pyobs_archive/api/views.py`). There is no notion of "which images may
this user see" at all — the `Frame` model has no project association
(`pyobs_archive/api/models.py`), and no source for one.

Observations are often proprietary: a user should only see images of projects they are a member
of, plus projects explicitly marked public. Project membership and the public flag are owned by
`pyobs-portal` (`Project` model: `code` PK, `name`, `priority`, `users` M2M, `public`
flag — `pyobs_portal/api/models.py`). The archive must learn projects and users from
there.

## What exists today

- **Backend is ready.** `GET /api/projects/` (`ProjectList`, `api/views.py`) returns exactly the
  requesting user's accessible projects — `Q(public=True) | Q(users__in=[user])`
  (`accessible_projects_q`); a superuser service account sees all projects, with `users`
  (usernames) and `public` in the payload (`ProjectSerializer`, `fields = "__all__"`). API auth
  is the same stack as the archive (`TokenAuthentication` + `SessionAuthentication` +
  `KeycloakAuthentication`). `GET /api/tasks/` returns task `id` + `project` (code).
- **Frame → project link exists indirectly.** FITS headers carry `REQNUM = str(task.id)` and
  `OBSNUM` (per-night counter) — see pyobs-core `specs/design/obsnum_fits_header.md` (#738,
  implemented); `Task.id → Task.project` in the backend DB. `Frame` already stores both
  (`REQNUM`, `OBSNUM` fields).
- **Archive auth.** Django users + optional Keycloak via `pyobs-auth`; `Profile` stores the
  user's encrypted Keycloak `access_token`/`refresh_token` (usable for token forwarding later).
- **Frontend** (`static/js/app.js`) consumes `/frames/`, `/frames/aggregate/`, `/frames/zip`
  and per-frame `download`/`related`/`preview`/`headers` — every frame-exposing endpoint is
  reachable from the UI and must be filtered.
- **Companion plan:** pyobs-core
  `specs/plans/2026-08-19-archive-project-access-control.md` covers the same issue from the
  core/pipeline angle. Its open question "who writes the `PROJECT` FITS keyword" is answered
  here (D4): **the mastermind** writes it, alongside `REQNUM`/`OBSNUM`. This plan is the
  archive-side implementation view and stays consistent with it.

## Design decisions

1. **Access granularity: per project.** Matches the backend's model exactly (#79). Per-
   observation or per-image access can layer on later via `OBSNUM`/`REQNUM`.
2. **Feature-gated: `PROJECT_ACCESS_CONTROL` (bool, default `False`).** Off → today's behavior,
   so existing installs opt in deliberately (also avoids breaking installs with no backend
   configured). On but no backend configured → fail closed (no projects known, only superusers
   see frames).
3. **Backend connection: local sync first (Option B), live per-request query later (Option A).**
   A `sync_projects` management command mirrors projects + memberships from the backend's
   admin-authenticated API using a service-account token (`PORTAL_URL` +
   `PORTAL_TOKEN`), so access checks are local, fast, and work for local
   Django-username users. Option A (forward the user's own Keycloak Bearer token from
   `Profile.access_token`, or a backend "accessible projects for user" endpoint) is the later
   enhancement behind the same interface.
4. **Frame → project association: `PROJECT` FITS keyword when present, `REQNUM` fallback.**
   Add `Frame.PROJECT` (max 10 chars, matching `Project.code`). Primary source is a `PROJECT`
   FITS keyword read during ingestion, **written by the mastermind**: pyobs-core
   `Mastermind.get_fits_header_before()` (`pyobs/modules/robotic/mastermind.py`) already emits
   `TASK`/`REQNUM`/`OBSNUM` from `self._task`, and `Task.project` (the code) is already a
   `Task` field — so it adds `hdr["PROJECT"] = FitsHeaderEntry(self._task.project, "Project
   code")` (upstream change, tracked in the pyobs-core companion plan). Until that lands,
   associate at ingest time via `REQNUM → Task.id → project` using the synced task map (REQNUM
   exists in headers today); frames with neither stay `None` (D5).
5. **Frames with `PROJECT = None` (legacy/unassociated): visible to superusers/staff only**
   (decided). Fail closed; the backfill command (§6) associates what it can.
6. **Superusers (and staff) see everything** — consistent with the existing `IsAdminUser`
   create/delete views.
7. **Unauthenticated users see nothing.** All endpoints stay `IsAuthenticated`; the frontend
   already redirects to login. Opening public frames to anonymous is a separate future toggle.
8. **Direct single-frame access is filtered too — answer 404, not 403**, so existence of
   private frames is not leaked (not even via counts/aggregates). Invariant for facets: the
   aggregate endpoint exposes **values, not counts**, and must always compute them from the
   access-filtered queryset (filter first, then aggregate) — never from the full table.
9. **`zip_view` (POST) silently skips unauthorized frames** — consistent with "only show what
   you can access"; a mixed selection still downloads the allowed subset. "Silently" means no
   404/403 and no per-id error in the response body (that would leak existence, contradicting
   D8) — but the zip's own manifest/file list already only names what it included, so the
   requester can tell an id was dropped by its absence, same as any zip with a partially invalid
   id list today. No new response field needed.
10. **`related` frames are filtered in both directions** (decided): an accessible frame's
    `related` list (and `get_info()['related_frames']`) drops frames the user cannot access.

## Implementation

### 1. Frame → project association — `pyobs_archive/api/models.py`

- [x] `PROJECT = models.CharField(max_length=10, null=True, default=None, db_index=True)` on
      `Frame` + migration `api/migrations/0012_frame_project.py` (numbering follows the existing
      sequence — `0011_alter_frame_id.py` is the current head).
- [x] Add `'PROJECT'` to the keyword list in `add_fits_header()` (absent header → stays `None`).
- [x] Expose `PROJECT` in `get_info()` (frontend column + API consumers).
- [x] `Frame.ingest()`: when `PROJECT` is absent but `REQNUM` is present, resolve
      `REQNUM → project` via the synced task map (§2) and set `PROJECT`; backend/sync
      unavailable → log a warning, leave `None` (private, D5).
- [ ] **Upstream (pyobs-core, tracked in the companion plan):** `Mastermind.
      get_fits_header_before()` adds `hdr["PROJECT"] = FitsHeaderEntry(self._task.project,
      "Project code")` next to `TASK`/`REQNUM`/`OBSNUM`; `Task.project` already holds the code.
      Until released, ingest relies on the `REQNUM` fallback.

### 2. Backend client — `pyobs_archive/api/portal.py` (new, later renamed from `backend.py`)

- [x] `PortalClient(base_url, token, timeout=5)` wrapping:
      - `get_projects()` → `GET {url}/api/projects/` with `Authorization: Token <token>` —
        **follow pagination** (backend paginates, page size 100) → list of
        `{code, name, public, users: [username, …]}`.
      - `get_tasks()` → `GET {url}/api/tasks/` → list of `{id, project}` (the REQNUM→project
        map for ingest + backfill).
- [x] Raise `PortalUnavailable` on network/timeout/5xx; callers decide (sync aborts loudly,
      ingest logs and continues unassociated).
- [x] Same interface reused by Option A later (per-user resolution) — no view changes needed
      when that lands.

### 3. Project/user mirror + sync — `pyobs_archive/api/models.py`,
   `pyobs_archive/api/management/commands/sync_projects.py`

- [x] Mirror models: `Project(code PK, name, public)` + memberships (either a `users` M2M to
      `django.contrib.auth.models.User` or a membership table keyed by username — matches the
      backend's `users` payload and keeps access checks local).
- [x] `manage.py sync_projects`: pull via `PortalClient.get_projects()` (service token),
      upsert mirror (delete locally-removed projects, update `public`, reconcile members by
      username). Log a diff summary; non-zero exit on backend failure.
- [x] README/.env.example: document running it periodically (cron/systemd timer, e.g. every
      5–10 min) and on backend project changes.

### 4. Access layer — `pyobs_archive/api/permissions.py` (new)

- [x] `accessible_projects(user) -> set[str] | None`: `None` for superusers/staff (everything),
      else `{code}` for `public=True` projects ∪ projects the user is a member of (mirror).
- [x] `can_access_frame(user, frame) -> bool`: superuser/staff → `True`; else
      `frame.PROJECT is not None and frame.PROJECT in accessible_projects(user)`.
- [x] `frame_access_q(user) -> Q` for queryset filtering (`frames_view`, `aggregate_view`,
      `zip_view_get`): `Q(PROJECT__in=accessible_projects(user))` for non-superusers.

### 5. Endpoint filtering — `pyobs_archive/api/views.py`

| View | Change |
|---|---|
| `frames_view` | after `filter_frames()`, restrict queryset via `frame_access_q` when the setting is on (skip for superusers). |
| `aggregate_view` | same restriction — **filter first, then aggregate**; the endpoint returns only distinct facet values of the accessible subset (no counts), so nothing beyond the user's own view is exposed (D8). |
| `zip_view_get` | same restriction on the queryset. |
| `zip_view_post` | per requested id: `can_access_frame`; **skip** unauthorized frames (D9). |
| `_frame(frame_id)` | central access check → raise `Http404` when the user lacks access (covers `frame_view`, `download_view`, `preview_view`, `headers_view`, `catalog_view`; no-op for the admin-only `delete_view`). |
| `related_view` | filter the related queryset by access (an accessible frame's related set may contain other projects' frames). |
| `create_view`, `delete_view` | unchanged (`IsAdminUser`). |

- [x] `Frame.get_info()`: drop `related_frames` ids the user cannot access (pass the request
      user through, or post-filter in the views).
- [x] All checks gated on `settings.PROJECT_ACCESS_CONTROL` (off → today's behavior).

### 6. Backfill — part of `sync_projects` or a `sync_frames_projects` command

**Skipped by decision (2026-08-24).** Not implementing a backfill command. Consequence:
historical frames ingested before this feature existed keep `PROJECT = None` forever unless
someone associates them manually — under D5 that means they stay superuser-only indefinitely
once `PROJECT_ACCESS_CONTROL` is flipped on, for any deployment that doesn't run a backfill of
its own. Only newly-ingested frames get associated, via the `REQNUM` fallback in `Frame.ingest()`
(§1) or the upstream `PROJECT` FITS keyword once it lands. If a deployment needs historical
frames visible, someone can still write the backfill later — the plan text above (§6 fetch
task→project map, update `PROJECT IS NULL` frames with a `REQNUM`) remains a valid design if
picked back up.

### 7. Settings/config — `pyobs_archive/settings.py`, `.env.example`, `README.md`

- [x] `PORTAL_URL = os.environ.get('PORTAL_URL', '')`
- [x] `PORTAL_TOKEN = os.environ.get('PORTAL_TOKEN', '')` (DRF token of a
      backend superuser/service account)
- [x] `PROJECT_ACCESS_CONTROL = os.environ.get('PROJECT_ACCESS_CONTROL', 'false').lower() in
      ('1', 'true', 'yes')`
- [x] `PORTAL_TIMEOUT = float(os.environ.get('PORTAL_TIMEOUT', '5'))`
- [x] README env table + `.env.example` rows; note that unset/empty disables access control.

### 8. Frontend — `pyobs_archive/frontend` (optional)

- [ ] No client change strictly needed (bootstrap-table + `app.js` consume `/frames/` +
      `/frames/aggregate/`, which already return only accessible rows).
- [ ] Optional: show `PROJECT` as a column; empty-state handling when nothing is accessible.

## Tests

Following the repo's existing convention (`pyobs_archive/api/tests.py`: one flat test file, one
`TestCase` subclass per unit under test — see `FrameAddFitsHeaderTests`, `FilterFramesTests`,
`FrameIngestPathSafetyTests`):

- `FrameProjectIngestTests`: `PROJECT` read from header; absent → `None`; `REQNUM` fallback
  resolves via the task map (mocked client); client unavailable → stays `None`, no crash.
- `AccessiblePermissionsTests` (`api/permissions.py`): superuser/staff → all; member → member +
  public projects; non-member → excluded; anonymous → existing 401; `PROJECT = None` frames →
  superuser-only.
- `FrameAccessEndpointTests` (client + mocked `PortalClient`): `frames_view` / `aggregate_view`
  / `zip_view_get` return only accessible rows; `zip_view_post` silently skips unauthorized ids
  (asserted by absence from the returned zip's manifest, not an error); `frame_view` /
  `download_view` / `headers_view` / `preview_view` / `catalog_view` → 404 for inaccessible
  frames; `related_view` and `get_info()['related_frames']` filtered.
- `SyncProjectsCommandTests`: upserts + reconciles, follows pagination, aborts cleanly (non-zero
  exit) when the backend is unreachable; `PROJECT_ACCESS_CONTROL` off → all previous tests
  unchanged (feature gate).
- Manual smoke test: one public + one private project, member and non-member users; verify
  listings, downloads, zip, and that 404s don't reveal existence.

## Rollout sequence

Cross-repo, so order matters — each step is independently safe to deploy (feature-gated or
additive) before the next:

1. **pyobs-core**: release `Mastermind.get_fits_header_before()` writing `PROJECT` (companion
   plan, §1 upstream item). Not a hard blocker for the rest — ingest's `REQNUM` fallback (D4)
   covers frames until this lands and gets adopted by observing sites.
2. **pyobs-portal**: `Project`/`users`/`public` API is already live (see "What exists
   today") — no action needed here before starting.
3. **pyobs-archive**, `PROJECT_ACCESS_CONTROL` still unset/`False` (no behavior change for
   existing installs):
   a. Ship the `PROJECT` column + migration, the backend client, the mirror models, and
      `sync_projects` — run it once manually to confirm connectivity and populate the mirror.
   b. Run the backfill (§6) to associate existing frames via `REQNUM`.
   c. Ship the endpoint filtering (§5), still inert while the flag is off.
4. **Flip `PROJECT_ACCESS_CONTROL=true`** per deployment, only once steps 3a–3c have been
   running long enough that the mirror and backfill are trusted (recommend: confirm `PROJECT`
   coverage on recent frames via a quick DB count before flipping, since anything still `NULL`
   goes superuser-only the moment the flag is on).
5. **Schedule `sync_projects`** as a periodic job (cron/systemd timer, §3) from the same
   deployment step as the flag flip — running the flag without the periodic sync means
   membership changes on the backend never propagate.

## Consequences

- **Good:** proprietary observations stop being visible to everyone; the access rule (public vs.
  members) matches the backend's ownership of projects and users.
- **Good:** feature-gated (`PROJECT_ACCESS_CONTROL`, default off) — existing installs keep
  today's behavior until they opt in; no backend configured = no behavior change.
- **Good:** sync keeps list queries local and fast; works for local Django-username users.
- **Neutral:** mirror is stale between syncs (minutes); unassociated frames are superuser-only
  until the backfill associates them.
- **Trade-off:** 404 (not 403) hides existence of private frames from non-members — including
  counts/aggregates.
- **Interplay with the backend proxy (pyobs-portal#82):** the backend's service token
  bypasses archive filtering when it proxies data to the archive — the backend's own access
  scoping stays the gate there; revisit (forward user identity / direct SSO links) when this
  plan lands.

## Resolved questions

All open questions from the original issue are resolved:

1. **Unassociated frames (`PROJECT = None`)** → superusers/staff only; fail closed (D5).
2. **Who writes the `PROJECT` FITS keyword** → the mastermind (pyobs-core,
   `Mastermind.get_fits_header_before()`, alongside `REQNUM`/`OBSNUM`; `Task.project` already
   holds the code); until that lands, ingest falls back to `REQNUM → task id → project` (D4).
3. **Sync vs. live query vs. token forwarding** → sync first (D3): `sync_projects` mirror via
   service token; Option A (per-user resolution) later behind the same client interface.
4. **`related` frames of an accessible frame** → not visible unless their own project is
   accessible; filtered in both directions (D10).
5. **Aggregate/facet existence leaks** → none: the endpoint returns values, not counts, and the
   filter-before-aggregate invariant means facets only reflect the user's own view (D8).
