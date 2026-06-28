# Changelog

## v1.5.1 - 2026-06-28

- Added configurable group-logo zoom animation for the kiosk group selection, including speed presets from "Sehr schnell" to "Langsam".
- Added an admin setting to disable the group-logo zoom and fall back to a more subtle touch animation.
- Reworked the admin system settings page into clearer sections for admin timeout, kiosk inactivity and group selection behavior.
- Fixed group-logo animation behavior so zoom-enabled logo tiles no longer play the small tap animation before the center zoom.
- Kept the new settings backward-compatible with existing v1.5.0 installations by storing them as optional `app_settings` keys with safe defaults.

## v1.5.0 - 2026-06-24

- Added richer kiosk news customization with alignment, text size and selectable PNG icons in the admin panel.
- Added configurable pricelist screensaver enable/disable setting and fixed kiosk idle navigation back to the home page.
- Added group tile display controls for logo-only group tiles and configurable logo sizing, including safer PNG logo trimming for consistent display.
- Added rotating application logging, quieter server logs, and an admin `syslogs` viewer with newest entries shown first.
- Added guided update protection: automatic pre-update backups, stored rollback target and master-protected code rollback to the commit before the last guided update.
- Improved admin statistics usability with collapsed long top lists and hardened warning-threshold form handling.

## v1.4.4 - 2026-05-13

- Unified admin `<select>` styling for Android WebView / in-app browsers (e.g. SBrowser on Android 12): touch-friendly height, minimum 16px text, consistent padding and native appearance.
- Reworked settlement (user billing) filter layout: dedicated `admin-settlement-filters` block inside the light panel instead of reusing the dark toolbar pattern, with full-width selects and safer flex sizing.
- Extended the same select rules to the users list group filter, new/edit user forms, and statistics group filter (including readable `option` colors on the dark toolbar).

## v1.4.3 - 2026-05-08

- Fixed release update behavior so systems updated to a newer commit are no longer downgraded back to the latest release tag on next `run.sh`/`install.sh`.
- Improved Android kiosk rendering stability (full-height behavior, top-ten footer consistency) and refined pricelist presentation.
- Added clearer in-app progress feedback for longer-running operations (downloads and year-end archive generation).
- Hardened update-availability detection in admin/dashboard by resolving the remote default branch and comparing installed vs. remote release state more reliably.

## v1.4.2 - 2026-05-06

- Changed admin password update flow: changing the regular admin password now requires the master password instead of the old admin password.
- Protected backup export and backup import with master-password verification in backend and admin UI.
- Added clearer backup error hints when master password is missing or invalid.
- Updated footer repository link wording in the base template.

## v1.4.1 - 2026-05-06

- Added optional opening-balance import when creating users to migrate legacy debt into the new system.
- Enforced debt-only semantics for opening balances: only negative UI values are accepted and mapped to internal open debt.
- Improved admin system-update messaging by distinguishing official release updates from commit-only updates.
- Simplified update preparation view by removing branch display and clarifying action guidance.

## v1.4.0 - 2026-04-29

- Added per-product group visibility controls in admin so products can be shown only to selected user groups on kiosk booking pages.
- Added per-product `show in pricelist` option to decouple pricelist visibility from kiosk booking visibility.
- Improved product edit UX with clearer wording, reliable back-navigation from product list to admin dashboard, and clearer checkbox rendering.
- Hardened master-password file handling by moving default to `.master_pwd`, adding `.master_pwd.example`, and auto-initializing missing master password file via `run.sh`.
- Updated docs with Android kiosk setup quickstart and cross-links between backend (`termux-kasse`) and Android app (`kiosk-app`) repositories.

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
