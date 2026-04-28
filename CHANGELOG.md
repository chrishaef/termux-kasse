# Changelog

## v1.3.0 - 2026-04-28

- Added robust PDF layout handling with safer page breaks and repeated headers across multi-page sections.
- Improved statistics PDF output: dedicated per-user tables, product order aligned to shop order, and clearer user detail labels.
- Unified monetary formatting in PDFs to `12,34 €` and aligned amount column captions to `€`.
- Updated admin UX: user list group filter, moved create forms below lists for groups/products, and toolbar quick actions.
- Refined update telemetry and guidance (`outdated` vs. `new-commit`) including clearer release/commit explanation texts.
- Improved warning threshold handling with configurable warning sound volume percentages and updated admin form layout.

## v1.2.1 - 2026-04-22

- Corrected README function descriptions to match current behavior exactly.
- Clarified Top-10 behavior (ranking modes by bookings or payments, compact table columns).
- Standardized wording from "Daten-Reset" to "System Reset" in documentation.
- Updated yearly-closeout notes: ZIP is archived and only latest year-end archive is retained.

## v1.2.0 - 2026-04-22

- Added admin system status details with version+commit display and freshness badge (`latest`/`outdated`/`unknown`).
- Added inline `update / reboot` action on the admin dashboard.
- Added dedicated update preparation flow with:
  - network status (`online`/`offline`) badges,
  - installed vs. latest available version+commit,
  - master password confirmation before starting update/restart.
- Added update progress screen with countdown and automatic return to `/admin`.
- Added offline guidance for restart-only mode when no internet connection is available.
- Updated admin backup card subtitle to `Backup & Recovery & Reset`.
