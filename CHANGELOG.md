# Changelog

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
