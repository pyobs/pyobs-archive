# Plan: Fix archive issue #74

Status: implemented and merged into pyobs-archive `develop` via [PR #79](https://github.com/pyobs/pyobs-archive/pull/79) on 2026-10-15. Issue #74 is closed.

Validation: 115 tests passed on SQLite; 114 passed on PostgreSQL with the SQLite-specific concurrency test skipped. GitHub CI, real Linux fpack round trips, browser computed theme colors, Django system checks, and Compose image resolution passed. Native macOS smoke testing remains unperformed.

Issue: [pyobs/pyobs-archive#74](https://github.com/pyobs/pyobs-archive/issues/74),
“Findings from running the archive on a MacBook M5 Pro (no Docker), 2.1.4”.

**Target repository:** `pyobs/pyobs-archive`, inspected on `develop` on
2026-10-15. This plan records the design implemented in PR #79. The behavior
below describes the findings before that fix.

## Scope and current behavior

Address all five findings:

1. `pyobs_archive/api/models.py::Frame.ingest` invokes `/usr/bin/fpack`, which
   excludes installations whose executable is elsewhere on `PATH`.
2. Ingest saves the frame and its related links before compression and writes
   compressor stdout directly to the final file before checking the exit code.
   Failure can leave a database row without a usable file or overwrite a valid
   existing file. Basename is unique; ingestion currently updates an existing
   frame with that basename, preserving its primary key.
3. `pyobs_archive/api/views.py::preview_view` uses Matplotlib's default upper
   origin, displaying FITS rows upside down.
4. `docker-compose.yaml` and `docs/source/installation.rst` use
   `ghcr.io/pyobs/pyobs/pyobs-archive:latest`. The release workflow publishes
   `ghcr.io/pyobs/pyobs-archive:latest`.
5. Loading-overlay and animation-dot selectors in
   `pyobs_archive/frontend/static/css/styles.css` lose to the more specific
   vendored Bootstrap Table selectors.

Keep the existing archive layout, basename formatting, project resolution,
related-frame semantics, endpoint response shape, and per-file upload behavior.
No database migration or new service is needed. Automatic repair of historical
broken records, a transactional storage redesign, Windows support, and unrelated
preview or theme changes are outside this fix.

## 1. Make compression portable and fail before publication

Refactor ingest into preparation/compression and publication phases, with small
private helpers where they make cleanup and failure injection clear.

- Continue validating `PATH_FORMATTER`, `FILENAME_FORMATTER`, and containment in
  `ARCHIVE_ROOT`; retain the existing traversal regression tests. Preserve
  normalization of `SCI.FNAME` and the `.fits.fz` suffix.
- Use a context manager for `fits.open()` and close the FITS object on every
  path, including invalid headers and serialization errors. Continue supporting
  both filenames and Django uploaded file objects.
- Discover `fpack` with `shutil.which('fpack')` after input validation but before
  database or final-file mutation. Execute the resolved path with an argument
  list and the existing `-S -` flags; do not invoke a shell.
- Report a clear missing-executable error naming `fpack` and the process `PATH`.
  Include exit status and a bounded, decoded stderr excerpt on compressor
  failure. Also handle an executable disappearing or becoming non-executable
  after discovery. Preserve the original exception as the cause when wrapping.
- Compress before changing any persistent frame metadata or relationships.
  Check success before treating stdout as an image. Reject empty output and
  verify that the result is readable FITS with a usable `SCI` HDU before
  publication. This also catches a successful exit with unusable output.
- Document the external CFITSIO/fpack prerequisite in
  `docs/source/development.rst`, including that the server process must inherit
  the installation's `PATH`; a shell's PATH alone is not sufficient for a
  separately launched service. The Dockerfile already installs `libcfitsio-bin`.

## 2. Coordinate file replacement and database updates

The contract for ordinary, catchable failures is: a failed new ingest leaves no
new frame/relationships/final file; a failed replacement leaves the original
frame, primary key, related links, and file bytes intact. A successful ingest
returns the basename only after both publication and database commit succeed.

### Publication sequence

1. Create destination directories with `exist_ok=True`. Write the validated
   compressed bytes to a uniquely named temporary file **in the destination
   directory**, close it, and flush/fsync it before publication. A staging write
   failure must never truncate the final pathname. Empty directories left by a
   failed ingest are acceptable.
2. Serialize publication for a basename before reading the existing frame.
   Use a filesystem advisory lock keyed by a stable hash of the basename under
   `ARCHIVE_ROOT/.ingest-locks/`, with independent file descriptors for each
   call. `fcntl.flock` supports the target macOS and Linux environments and
   protects both multiple Gunicorn processes and threaded callers. Keep lock
   files rather than unlinking them on release, which can split waiters across
   different lock inodes. Compression can run before acquiring the lock.
   All participating writers must use the same archive root on a filesystem
   supporting these locks; this is not a distributed-storage locking solution.
3. Start an outermost database transaction covering the frame and M2M writes.
   Use `transaction.atomic(durable=True)` so an enclosing transaction cannot
   silently roll back the database after this helper has discarded its backup.
   Current callers are the management command and the per-file upload loop;
   neither wraps ingest in another transaction. Document this boundary, and use
   `TransactionTestCase` for tests that exercise real commit/rollback behavior.
4. Read the existing row inside the serialized section, using
   `select_for_update()` where supported. Retain the unique basename constraint
   as a database backstop; row locking alone cannot protect a nonexistent row
   and is ineffective on SQLite. Create a new frame only when absent. Populate
   metadata, preserve the current project fallback behavior, save, and update
   related links within this transaction. Capture the previous file location
   before changing `img.path`.
5. Before replacing an existing destination, create and close a unique sibling
   backup containing its original bytes. A backup failure aborts without touching
   that destination. Protect an existing destination even if it has no matching
   row; do not assume every pre-existing file is disposable.
6. Publish with `os.replace(staged_path, final_path)` after all metadata and link
   writes succeed. Staging beside the final file keeps the rename on one
   filesystem. Readers see a complete old or new file, never partial output.
7. Exit the transaction and complete the commit while still holding the basename
   lock. Track whether publication occurred and whether commit completed;
   cleanup decisions must use those states rather than only file existence.
8. After commit, remove the backup and any superseded old-path file when the
   formatter moved an existing basename to a different directory. Keep the old
   file until this point. A post-commit cleanup failure is logged as maintenance
   work and must not turn a successfully committed ingest into a reported
   failure or undo its newly published file. Release the lock after cleanup.

### Failure handling

| Failure point | Required result |
| --- | --- |
| Header validation, discovery, serialization, compression, output validation | No database mutation and no final-file mutation; close resources. |
| Directory creation, stage write/flush, backup creation | Abort; original file and database remain intact; remove this attempt's temporary files. |
| Frame save or related-link update | Roll back all database writes; final file remains intact. |
| Atomic replacement | Roll back database writes; retain/restore the prior destination as needed. |
| Database commit fails after publication, with rollback confirmed | Remove this attempt's new destination or restore its backup atomically, then propagate the error. |
| Compensation itself fails | Preserve the backup and all recovery evidence; log original and cleanup errors with affected paths and report failure. Never silently delete the only recoverable original. |
| Cleanup after confirmed commit fails | Keep committed frame and new image; log leftover backup/old path for later cleanup and return success. |

Perform compensation outside the transaction context, after rollback, while the
basename lock is still held. Cleanup must affect only files owned by this
attempt, and must not mask the primary failure. If a database connection failure
makes the commit outcome ambiguous, do not blindly restore or delete the final
file: retain backup evidence, report the uncertain outcome, and reconcile against
the database before further ingest of that basename.

Filesystem rename and database commit are not a single atomic operation. This
bounded fix handles ordinary failures and competing ingests, but cannot promise
crash/power-loss atomicity or simultaneous visibility of metadata and file bytes
to readers. A process death between rename and commit can require manual recovery;
record this explicitly in development/operations documentation. Persistent
journaling or versioned immutable storage would be a separate design. Existing
delete operations also do not participate in this ingest lock; concurrent manual
deletion is outside the guarantee.

Do not attempt publication solely in `transaction.on_commit`: publication can
then fail after the row has already committed. Do not use `atomic()` alone:
database rollback cannot restore overwritten file bytes.

## 3. Apply the preview, image-name, and theme fixes

- Pass `origin='lower'` to the `ax.imshow` call in `api/views.py::preview_view`.
  Preserve existing trimming, grayscale, percentile cuts, dimensions, and
  access-control behavior.
- Change Compose's web image and the installation documentation to
  `ghcr.io/pyobs/pyobs-archive:latest`, matching `.github/workflows/docker.yml`.
- Make loading CSS selectors strictly more specific than all applicable vendor
  rules, including `.table-dark` variants, without editing vendor files or using
  broad `!important` declarations. A concrete selector base is
  `html .bootstrap-table .fixed-table-container .fixed-table-body
  .fixed-table-loading`, with explicit corresponding `.table-dark` rules.
  Append `.loading-wrap .animation-dot` and
  `.loading-wrap .animation-wrap::before/::after` for all three animated dots.
  Keep the existing `--pyobs-surface-bg` and `--pyobs-loading-dot` theme tokens.
  Strictly greater specificity avoids dependence on the shared base template's
  stylesheet order.

## 4. Validation

Follow the existing Django/unittest conventions in `pyobs_archive/api/tests.py`.
The repository uses `uv run python manage.py test`, and its CI runs Python 3.11
with SQLite. Use temporary directories with automatic cleanup, genuine small
FITS fixtures with a nonempty `SCI` array, `override_settings`/`self.settings`,
and mocks at external-process or fault-injection boundaries. No real compressor
is required for the ordinary unit suite.

Add focused ingestion tests for:

- A successful new ingest: one row, correct metadata and links, valid final
  FITS bytes, normalized basename, no stage/backup leftovers.
- PATH discovery of a nonstandard executable, missing `fpack`, launch failure,
  nonzero exit with partial stdout, empty stdout, and malformed FITS output.
- Serialization, stage write/flush, backup, save, related-link, replacement,
  and actual transaction-commit failures. Assert database and filesystem state,
  not merely that an exception is raised.
- Successful replacement retains the original row's primary key and replaces
  metadata/links and file bytes. Failed replacement restores both old links and
  exact old bytes. Repeat with a changed formatted directory and with a
  pre-existing destination lacking a database row.
- Post-commit cleanup failure preserves success; compensation failure preserves
  recovery data and surfaces a useful diagnostic. An enclosing transaction is
  rejected before final-file mutation.
- Two concurrent publications of the same basename cannot interleave backup,
  replacement, and compensation. Use independent processes/connections and
  synchronization barriers, not timing sleeps; do not use in-memory SQLite for
  this check. Check both first creation and replacement. Exercise the lock on
  macOS/Linux and the transaction integration on the deployment's PostgreSQL.
- Keep existing path-safety and project-resolution tests passing, and verify
  the upload endpoint still reports failed files in `errors` while counting
  successful files correctly.

For preview orientation, render a small asymmetric image with distinct upper
and lower bands through the authenticated endpoint and decode its PNG. Compare
interior pixel bands to verify the first FITS row appears at the bottom; avoid
font- or whole-PNG snapshots. Retain inaccessible-frame 404 coverage.

For CSS, inspect the actual computed background colors in both light and dark
themes while Bootstrap Table shows its loading overlay during refresh/sort/
pagination. Include the central dot and both pseudo-elements, plus `.table-dark`
if applied. A browser smoke check is more useful than a source-string test.

Run the focused new Django tests, then the full suite with an isolated test
database. Run `uv run python manage.py check`. Validate Compose with
`docker compose config --images` using a disposable valid env file where needed;
compare the rendered web image against the release workflow. No image push or
deployment is required.

Finally, on a native macOS installation with fpack available outside `/usr/bin`,
ingest and preview a real small FITS image, retry the same basename, and confirm
successful download/decompression. Repeat compression smoke coverage in the
Linux/container environment. Record unavailable platform checks as outstanding
validation rather than claiming they passed.

## Delivery and acceptance

Implement in reviewable steps: ingestion refactor and failure tests; preview
fix and orientation regression; Compose/documentation correction; CSS specificity
fix and browser verification. Run the full suite after the combined change.

Acceptance requires all five findings to be addressed, caught failures to leave
no newly broken frame or destroy a previously valid image, successful basename
replacement to retain identity, and the native macOS smoke check to confirm PATH
discovery. Document the database/filesystem crash boundary and any unperformed
environment-specific checks. Do not run the existing destructive `checkfiles`
repair command automatically against users' archives; historical damage needs
separate review and recovery.
