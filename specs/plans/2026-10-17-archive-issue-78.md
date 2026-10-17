# Plan: Fix archive issue #78

Status: core fix landed as 8194b1a ("Fix UTC parsing of archive link time windows (#78)") and
is released in v2.1.5 (on `main`). Issue #78 is still open. The changelog entry and the backend
test are in the follow-up PR; the browser check and closing #78 are left.

Issue: [pyobs/pyobs-archive#78](https://github.com/pyobs/pyobs-archive/issues/78),
"Links into the archive with a time window find nothing when the viewer's computer is not on
UTC".

**Target repository:** `pyobs/pyobs-archive`, inspected on 2026-10-17 (`develop`,
`origin/main`, and the `codex/silent-frame-refresh` branch).

## Root cause (verified in code)

- `pyobs_archive/frontend/static/js/app.js`, page init: link parameters were parsed with
  `moment(params.get('start'))`, i.e. in the browser's local zone. `setDateRange()` then
  formats them as `YYYY-MM-DD HH:mm` with no offset, so the local wall-clock time ends up in
  `#date-start`/`#date-end`.
- `queryParams()` sends that text unchanged as `start`/`end`.
- `pyobs_archive/api/views.py::frames_view` filters `DATE_OBS__gte=start` /
  `DATE_OBS__lte=end`. With `USE_TZ = True` and `TIME_ZONE = 'UTC'`
  (`pyobs_archive/settings.py`), Django reads a naive string as UTC. On a UTC-4 machine the
  window lands 4 hours early.
- Every other place that fills the range (picker presets, default range, reset) uses
  `moment.utc()`, so the page's convention is "displayed wall-clock time is UTC". The link path
  was the only exception.
- The shift only happens for times **with an offset**. The portal builds links with
  `datetime.isoformat()` (`pyobs-portal/pyobs_portal/api/archive.py`), giving e.g.
  `2026-10-15T00:04:00+00:00`. Old `moment()` converted that to local time (20:04 in
  New York). A naive `2026-10-15 00:09` was parsed as local and formatted as local, so it
  round-tripped unchanged and worked. Verified with the vendored moment under
  `TZ=America/New_York` (node, 2026-10-17):

  | link value | `moment.utc` (fix) | `moment` (old) |
  |---|---|---|
  | `2026-10-15 00:09` | 00:09 | 00:09 |
  | `2026-10-15T00:04:00+00:00` | 00:04 | 2026-10-14 20:04 |
  | `2026-10-15T02:04:00+02:00` | 00:04 | 2026-10-14 20:04 |

  So the issue's "times in UTC" links must have carried an offset, as the portal's do.

## Fix approach

Parse link times as UTC (`moment.utc(...)`), matching the rest of the page. This is the
issue's own suggestion and is what 8194b1a does.

Alternative considered: keep showing local time and convert back to UTC before the request.
Rejected because the page shows UTC everywhere else, astronomers work in UTC, and it would
need offset-aware handling in every path that fills the range (presets, picker, reset), not
just the link.

## Checklist

- [x] `app.js`: `setDateRange(moment.utc(params.get('start')), moment.utc(params.get('end')))`
      (8194b1a on `develop`).
- [x] Add a CHANGELOG `[Unreleased]` entry: "Read the start and end times of archive links as
      UTC, so links work on computers not set to UTC (#78)."
- [x] Backend test in `pyobs_archive/api/tests.py` (`FilterFramesTimeWindowTests`) pinning the UTC contract of `filter_frames`, which `frames_view` uses:
      frames at 00:10 and 04:10 UTC; `start=2026-10-15 00:00&end=2026-10-15 00:30` returns only
      the first; the same window with an explicit `+00:00` offset also returns only the first.
      This guards the server side; the bug itself was frontend-only.
- [ ] Frontend check (no JS test setup exists in this repo, so manual or scripted):
      - [x] Node one-off against the vendored file (done 2026-10-17, see table above):
        `TZ=America/New_York node -e "const moment=require('./pyobs_archive/frontend/static/js/vendor/moment.min.js'); for (const s of ['2026-10-15 00:09','2026-10-15T00:04:00+00:00','2026-10-15T02:04:00+02:00']) console.log(moment.utc(s).format('YYYY-MM-DD HH:mm'))"`
        All three must print `2026-10-15 00:0x` UTC times.
      - Browser smoke test with a non-UTC zone (e.g. `TZ=America/New_York chromium`, or
        DevTools Sensors > Location timezone override): open a portal-style link with
        `start`, `end` and `OBSNUM`, confirm the displayed range is UTC and frames are listed.
- [x] Released in v2.1.5.
- [ ] Close #78 referencing v2.1.5, after the browser check.

## Risks and related issues (not fixed here, flag only)

- **End truncated to the minute.** `setDateRange()` formats with `HH:mm`, so a link
  `end=...00:34:30` becomes `00:34` and `DATE_OBS__lte` drops frames from 00:34:00.001 to
  00:34:30. The portal pads by 5 minutes, so it rarely matters there, but direct links without
  padding can lose the last frames. Possible fix: round `end` up to the next minute, or keep
  seconds. Separate issue if wanted.
- **Picker not synced with link values.** `setDateRange()` only writes the text spans; the
  `#daterange` picker's own `startDate`/`endDate` are never set, so opening the picker after
  following a link shows an unrelated range. Cosmetic.
- **Custom picker selections.** daterangepicker builds local moments, but only their wall-clock
  text is used, which the server reads as UTC. Consistent with the "wall clock is UTC"
  convention, but the UI never labels the times as UTC. A "(UTC)" label next to the range would
  remove the ambiguity.
- `'All Time'` uses `moment('2000-01-01')` (local); harmless since only the text is used.
- Presets are computed once at page load, so "Today" goes stale if the page stays open past
  midnight UTC. Minor.
