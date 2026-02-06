# FilamentHub OrcaSlicer Integration - End-to-End Testing Guide

**Refactoring Task:** 001-refactoring-orcaslicer-and-backend
**Phase:** 8 - End-to-End Testing
**Subtask:** 8-1 - Manual Testing of FilamentHub Login and Sync Functionality

**Date Created:** 2026-02-06
**Purpose:** Manual verification of refactored FilamentHub OrcaSlicer integration
**Tester:** _[Name]_
**Test Date:** _[Date]_

---

## Overview

This guide provides comprehensive manual testing procedures for the refactored FilamentHub OrcaSlicer integration. The refactoring moved business logic from C++ client to Python backend and modularized the C++ codebase from a 6,377-line monolith into 4 focused modules (~4,427 lines).

### What Was Refactored

**C++ Modules Created:**
- `AuthManager.cpp` (608 lines) - Token and authentication management
- `SyncCoordinator.cpp` (755 lines) - Sync orchestration using SyncPlan API
- `PresetImporter.cpp` (1,308 lines) - Preset download and import logic
- `FilamentHubPanel.cpp` (1,756 lines) - UI layer and WebView integration

**Backend Services (Phase 1 - Already Complete):**
- SyncOrchestrator service - Sync plan generation
- OrcaSlicerValidator service - Preset validation
- 5 new API endpoints for sync orchestration

---

## Prerequisites

### 1. Environment Setup

- [ ] OrcaSlicer built successfully from refactored code
  ```powershell
  cd F:\FilamentHub\docs\OrcaSlicer
  .\build_release_vs2022.bat slicer
  ```

- [ ] Backend services running
  ```bash
  cd F:\FilamentHub\backend
  uvicorn app.main:app --reload --port 8000
  ```

- [ ] Database migrations applied
  ```bash
  cd F:\FilamentHub\backend
  alembic upgrade head
  ```

- [ ] Test account credentials ready
  - Username: _________________
  - Password: _________________

### 2. Baseline Verification

- [ ] API endpoints accessible at http://localhost:8000/docs
- [ ] New sync endpoints visible:
  - POST `/api/v1/orcaslicer/sync-plan`
  - GET `/api/v1/orcaslicer/sync-status`
  - POST `/api/v1/orcaslicer/validate-parent`
  - POST `/api/v1/orcaslicer/validate-batch`
  - POST `/api/v1/orcaslicer/deleted-presets`

---

## Test Suite

### Test 1: Application Launch

**Objective:** Verify OrcaSlicer launches without errors after refactoring

**Steps:**
1. Launch OrcaSlicer executable
2. Wait for application to fully load
3. Check console/logs for errors

**Expected Results:**
- [ ] Application launches successfully
- [ ] No crash dialogs appear
- [ ] No error messages in console/logs related to FilamentHub modules
- [ ] UI renders correctly

**Actual Results:**
```
[Record any observations or issues]
```

**Status:** ⬜ Pass | ⬜ Fail | ⬜ Blocked

---

### Test 2: FilamentHub Tab Navigation

**Objective:** Verify FilamentHub tab loads correctly with refactored FilamentHubPanel

**Steps:**
1. Navigate to FilamentHub tab in OrcaSlicer
2. Observe UI rendering
3. Check WebView loads correctly

**Expected Results:**
- [ ] FilamentHub tab visible in navigation
- [ ] Tab content loads without errors
- [ ] WebView displays correctly (no white screen or error page)
- [ ] Login interface visible

**Actual Results:**
```
[Record any observations]
```

**Status:** ⬜ Pass | ⬜ Fail | ⬜ Blocked

---

### Test 3: User Authentication - Login

**Objective:** Verify login functionality using refactored AuthManager module

**Steps:**
1. Click login button or enter credentials
2. Enter test account username
3. Enter test account password
4. Click "Войти" (Login) button
5. Wait for authentication to complete

**Expected Results:**
- [ ] Login form accepts input
- [ ] Authentication request sent to backend
- [ ] AuthManager saves token to configuration
- [ ] UI updates to show logged-in state
- [ ] User info displayed correctly
- [ ] Russian text displays correctly ("Войти")

**Actual Results:**
```
Token received: [Yes/No]
User info displayed: [Yes/No]
Any errors: [Details]
```

**Status:** ⬜ Pass | ⬜ Fail | ⬜ Blocked

---

### Test 4: Filament Presets Synchronization

**Objective:** Verify filament presets sync using refactored SyncCoordinator and SyncPlan API

**Steps:**
1. Ensure logged in from Test 3
2. Navigate to filament presets section
3. Click "Синхронизировать" (Sync) button
4. Monitor progress bar/status
5. Wait for sync to complete
6. Check imported presets

**Expected Results:**
- [ ] Sync button clickable when logged in
- [ ] SyncCoordinator requests sync plan from backend
- [ ] Progress bar shows during sync (SyncJob process() method)
- [ ] Russian notification: "Синхронизация филаментов..." displays
- [ ] PresetImporter downloads and imports presets
- [ ] Sync completes without errors
- [ ] Filament presets appear in OrcaSlicer preset list
- [ ] Preset details (temperature, material type) correct
- [ ] No duplicate presets created

**Actual Results:**
```
Presets synced: [Count]
Time taken: [Duration]
Errors encountered: [Details]
```

**Status:** ⬜ Pass | ⬜ Fail | ⬜ Blocked

---

### Test 5: Printer Profiles Synchronization

**Objective:** Verify printer profiles sync using SyncCoordinator

**Steps:**
1. Navigate to printer profiles section
2. Click "Синхронизировать" button
3. Monitor progress
4. Wait for completion
5. Verify imported profiles

**Expected Results:**
- [ ] Sync initiates correctly via SyncCoordinator
- [ ] Progress updates displayed in Russian
- [ ] Printer profiles imported successfully via PresetImporter
- [ ] Profile details (bed size, nozzle diameter) correct
- [ ] Compatible filaments linked correctly

**Actual Results:**
```
Profiles synced: [Count]
Time taken: [Duration]
Errors: [Details]
```

**Status:** ⬜ Pass | ⬜ Fail | ⬜ Blocked

---

### Test 6: Print Profiles Synchronization

**Objective:** Verify print profiles sync

**Steps:**
1. Navigate to print profiles section
2. Click "Синхронизировать" button
3. Monitor progress
4. Verify imported profiles

**Expected Results:**
- [ ] Sync completes successfully
- [ ] Print profiles imported
- [ ] Profile settings (layer height, speed) correct
- [ ] Compatible printers/filaments linked

**Actual Results:**
```
Profiles synced: [Count]
Errors: [Details]
```

**Status:** ⬜ Pass | ⬜ Fail | ⬜ Blocked

---

### Test 7: Russian Localization

**Objective:** Verify all Russian notifications and UI text display correctly

**Checklist:**
- [ ] "Синхронизировать" button label correct
- [ ] "Войти" login button correct
- [ ] Progress notifications in Russian
- [ ] Success message: "Синхронизация завершена" (or similar)
- [ ] Error messages in Russian
- [ ] No encoding issues (no �, gibberish, or mojibake)
- [ ] Cyrillic characters render properly

**Issues Found:**
```
[List any localization issues]
```

**Status:** ⬜ Pass | ⬜ Fail | ⬜ Blocked

---

### Test 8: Sync Cancellation

**Objective:** Verify sync can be cancelled gracefully using SyncJob cancellation (Ctl::was_canceled)

**Steps:**
1. Initiate a large sync operation
2. Click cancel button during sync
3. Verify cancellation behavior

**Expected Results:**
- [ ] Cancel button available during sync
- [ ] SyncJob detects cancellation via Ctl::was_canceled()
- [ ] Sync stops when cancelled
- [ ] No crash or freeze
- [ ] Partial presets handled correctly
- [ ] Can start new sync after cancellation
- [ ] No zombie threads or processes

**Actual Results:**
```
Cancellation time: [Duration]
Partial presets: [Details]
Errors: [Details]
```

**Status:** ⬜ Pass | ⬜ Fail | ⬜ Blocked

---

### Test 9: Memory Leak Detection

**Objective:** Verify no memory leaks during extended sync operations (critical for C++ refactoring)

**Steps:**
1. Open Windows Task Manager
2. Note OrcaSlicer baseline memory usage: ________ MB
3. Perform multiple sync operations (5+ times)
4. Monitor memory usage after each sync
5. Wait 2 minutes after final sync
6. Note final memory usage: ________ MB

**Expected Results:**
- [ ] Memory usage returns to baseline after sync
- [ ] No continuous memory growth
- [ ] Memory delta < 50MB after 5 syncs
- [ ] No handles leak (check in Task Manager > Details > Handles column)
- [ ] Proper cleanup in SyncJob::finalize() and module destructors

**Memory Usage Log:**
```
Baseline: _____ MB
After sync 1: _____ MB
After sync 2: _____ MB
After sync 3: _____ MB
After sync 4: _____ MB
After sync 5: _____ MB
Final (after 2 min idle): _____ MB
```

**Status:** ⬜ Pass | ⬜ Fail | ⬜ Blocked

---

### Test 10: Error Handling - Network Failure

**Objective:** Verify graceful error handling when backend is unreachable

**Steps:**
1. Stop backend server (Ctrl+C on uvicorn process)
2. In OrcaSlicer, attempt to sync
3. Observe error handling in SyncCoordinator and PresetImporter

**Expected Results:**
- [ ] Error message displayed to user (in Russian)
- [ ] Ctl::show_error_info() called in SyncJob
- [ ] No application crash
- [ ] UI remains responsive
- [ ] Can retry after backend restarted

**Actual Results:**
```
Error message shown: [Yes/No]
Message text: [Details]
Application crashed: [Yes/No]
```

**Status:** ⬜ Pass | ⬜ Fail | ⬜ Blocked

---

### Test 11: Incremental Sync (Second Sync)

**Objective:** Verify incremental sync using SyncPlan API only downloads new/changed presets

**Steps:**
1. Complete full sync (Test 4)
2. Wait 5 seconds
3. Click sync again
4. Monitor network traffic or logs

**Expected Results:**
- [ ] SyncCoordinator requests sync plan with sync version
- [ ] Backend returns incremental plan (not full sync)
- [ ] Sync completes faster than first sync
- [ ] Only changed/new presets downloaded
- [ ] Sync status indicates "incremental" mode
- [ ] Existing presets not duplicated

**Actual Results:**
```
First sync time: _____ seconds
Second sync time: _____ seconds
Presets downloaded in second sync: _____
Sync plan type: [full/incremental]
```

**Status:** ⬜ Pass | ⬜ Fail | ⬜ Blocked

---

### Test 12: Deleted Presets Handling

**Objective:** Verify deleted presets detection using new `/deleted-presets` endpoint

**Prerequisites:**
1. Backend test account with deleteable preset
2. Delete a preset from backend/web interface

**Steps:**
1. Sync to get initial preset
2. Delete preset from backend (via web interface)
3. Sync again in OrcaSlicer
4. Observe deleted preset handling via SyncCoordinator

**Expected Results:**
- [ ] SyncCoordinator calls `/api/v1/orcaslicer/deleted-presets` endpoint
- [ ] Deleted preset detected by client
- [ ] User prompted about deletion (or auto-removed per settings)
- [ ] Local preset removed correctly
- [ ] No orphaned files left

**Actual Results:**
```
[Record behavior]
```

**Status:** ⬜ Pass | ⬜ Fail | ⬜ Blocked

---

### Test 13: Token Expiration & Refresh

**Objective:** Verify token refresh works using AuthManager

**Steps:**
1. Login to OrcaSlicer (AuthManager saves token)
2. Wait for token to approach expiration (check JWT expiry)
   - OR manually set short expiration in backend for testing
3. Perform sync operation
4. Verify AuthManager refreshes token

**Expected Results:**
- [ ] AuthManager automatically refreshes token before expiration
- [ ] Sync operation completes successfully
- [ ] No "unauthorized" errors
- [ ] User not prompted to re-login

**Actual Results:**
```
Token refreshed: [Yes/No]
Errors: [Details]
```

**Status:** ⬜ Pass | ⬜ Fail | ⬜ Blocked

---

### Test 14: Conflict Detection

**Objective:** Verify conflicts detected using SyncPlan API conflict detection

**Prerequisites:**
1. Preset exists both locally and on server
2. Modify preset locally (change temperature, for example)
3. Modify same preset on server (different change)

**Steps:**
1. Create conflict scenario as above
2. Perform sync
3. Observe conflict handling in SyncCoordinator

**Expected Results:**
- [ ] Backend SyncPlan includes conflicts list
- [ ] SyncCoordinator detects conflict from sync plan
- [ ] User prompted to resolve conflict
- [ ] Options presented: keep local / keep server / merge
- [ ] Resolution applied correctly

**Actual Results:**
```
Conflict detected: [Yes/No]
Resolution UI shown: [Yes/No]
[Details]
```

**Status:** ⬜ Pass | ⬜ Fail | ⬜ Blocked

---

## Summary

### Test Results Overview

| Test # | Test Name | Module Tested | Status | Notes |
|--------|-----------|---------------|--------|-------|
| 1 | Application Launch | All | ⬜ | |
| 2 | FilamentHub Tab | FilamentHubPanel | ⬜ | |
| 3 | User Login | AuthManager | ⬜ | |
| 4 | Filament Sync | SyncCoordinator, PresetImporter | ⬜ | |
| 5 | Printer Sync | SyncCoordinator, PresetImporter | ⬜ | |
| 6 | Print Profiles Sync | SyncCoordinator, PresetImporter | ⬜ | |
| 7 | Russian Localization | FilamentHubPanel | ⬜ | |
| 8 | Sync Cancellation | SyncJob | ⬜ | |
| 9 | Memory Leak Check | All modules | ⬜ | |
| 10 | Network Error Handling | SyncCoordinator | ⬜ | |
| 11 | Incremental Sync | SyncCoordinator | ⬜ | |
| 12 | Deleted Presets | SyncCoordinator | ⬜ | |
| 13 | Token Refresh | AuthManager | ⬜ | |
| 14 | Conflict Detection | SyncCoordinator | ⬜ | |

**Total Tests:** 14
**Passed:** _____
**Failed:** _____
**Blocked:** _____

### Critical Issues Found

```
[List any critical issues that block release]
```

### Non-Critical Issues

```
[List minor issues or improvements]
```

### Performance Metrics

- Average sync time (filament): _____ seconds
- Average sync time (printer): _____ seconds
- Average sync time (print): _____ seconds
- Memory usage increase: _____ MB
- Application startup time: _____ seconds

### Code Quality Verification

- [ ] No C++ compilation errors
- [ ] No C++ compilation warnings related to FilamentHub modules
- [ ] Line count reduction verified: 6,377 → 4,427 lines (30.6% reduction)
- [ ] All 4 modules properly separated by concern
- [ ] No code duplication between modules

### Recommendations

```
[QA recommendations for improvements or next steps]
```

---

## Sign-Off

**Tester Name:** _____________________
**Tester Signature:** _____________________
**Date:** _____________________

**QA Status:** ⬜ APPROVED | ⬜ APPROVED WITH ISSUES | ⬜ REJECTED

**Comments:**
```
[Final QA comments]
```

---

## Appendix A: Module Architecture

### AuthManager (608 lines)
- **Responsibility:** Token lifecycle management, authentication state
- **Key Methods:** `login()`, `logout()`, `is_authenticated()`, `refresh_token()`
- **Dependencies:** HTTP client (Boost.Beast), configuration system

### SyncCoordinator (755 lines)
- **Responsibility:** Sync orchestration, SyncPlan API integration
- **Key Methods:** `synchronize()`, `request_sync_plan()`, `handle_deleted_presets()`
- **Dependencies:** AuthManager, PresetImporter, HTTP client

### PresetImporter (1,308 lines)
- **Responsibility:** Preset download, validation, import
- **Key Methods:** `download_preset()`, `import_preset()`, `validate_parent()`
- **Dependencies:** HTTP client, preset system, file I/O

### FilamentHubPanel (1,756 lines)
- **Responsibility:** UI layer, WebView bridge, user interaction
- **Key Methods:** `on_sync_button()`, `on_login_button()`, `update_ui()`
- **Dependencies:** wxWidgets, WebView, all other modules

---

## Appendix B: Log Collection

### OrcaSlicer Logs
Location: `%APPDATA%\OrcaSlicer\log\` or similar

**Relevant log excerpts:**
```
[Paste relevant logs if issues found]
```

### Backend Logs
```
[Paste relevant backend logs if issues found]
```

### Network Traffic (API Requests)
```
[Paste relevant API requests/responses if needed for debugging]

Example:
POST /api/v1/orcaslicer/sync-plan
{
  "device_fingerprint": "...",
  "preset_type": "filament",
  "force_full_sync": false
}

Response:
{
  "to_download": [...],
  "deleted_on_server": [...],
  "conflicts": [...]
}
```

---

## Appendix C: Troubleshooting

### Common Issues

**Issue:** OrcaSlicer crashes on FilamentHub tab navigation
**Possible Causes:**
- FilamentHubPanel constructor error
- WebView initialization failure
- Missing module dependencies

**Issue:** Sync button does nothing
**Possible Causes:**
- Not authenticated (AuthManager state)
- Backend not running
- SyncCoordinator initialization failed

**Issue:** Presets not appearing after sync
**Possible Causes:**
- PresetImporter validation failed
- File write permissions
- Incorrect preset path configuration

**Issue:** Memory usage continuously increases
**Possible Causes:**
- HTTP client connection not closed
- SyncJob not cleaning up properly in finalize()
- WebView resource leak

---

## Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-06 | auto-claude | Initial testing guide for refactored integration |
