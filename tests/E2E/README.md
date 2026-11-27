# Android E2E environment

The optional manual GitHub Actions draft and its setup, ownership and validation
limits are documented in [CI.md](CI.md). Hosted CI remains unverified.

Scope: the native Tasks Android application, Google Play flavor. Browser E2E has
been discarded. Hybrid/WebView coverage has not been established by inspecting
the source; Custom Tabs alone do not establish an embedded web application.

The setup script uses Linux bash, matching repository CI. Windows users can use
WSL. Set an absolute private state directory outside this checkout; do not commit
APKs, credentials, device data or execution evidence.

```bash
export TASKS_E2E_STATE_DIR=/absolute/private/tasks/artifacts/runtime
bash tests/E2E/scripts/install-tasks.sh download
bash tests/E2E/scripts/install-tasks.sh verify
```

The release is pinned to `15.14.1`, asset `tasks-googleplay-15.14.1.apk`, SHA-256
`0823d18f54d50bb39bc462f5afdbaecab7e2594ee10564032e0152aa14528de8`.
Its Git tag resolves to `cad731b963b35f6feb3f09f4104756b627dd3340`.
This is a published binary, not proof that the current checkout was built.
The digest checks integrity against GitHub release metadata; it does not replace
an APK signing-certificate verification.

For a source build, install the repository's JDK 25 and Android SDK platform 37,
accept the required SDK licenses, then use the checked-in Gradle wrapper:

```bash
export ANDROID_HOME=/absolute/path/to/android-sdk
bash tests/E2E/scripts/install-tasks.sh build
```

This invokes `:app:assembleGoogleplayDebug`, requires no production signing key,
and copies the output into a unique private state path. Optional map keys are
documented in CONTRIBUTING.md; the first offline task journey should not depend
on maps, Google account authentication, billing or synchronization. The source
build and local app lifecycle were verified against checkout
`e9472b806434ddba2263ce4108730f7010cd5d32`. The SDK platform package installed
by Gradle was `platforms;android-37.0`; requesting `platforms;android-37`
directly was not accepted by the SDK manager used during verification.

For local installation, provision an isolated Android emulator named
`tasks-testrigor-e2e` and explicitly select its serial. The cloud suite's Android
36 / Pixel 9 x86_64 configuration is the initial compatibility target. Emulator
creation, image provisioning and startup are prerequisites, not performed by
this installer.

```bash
export TASKS_ANDROID_SERIAL=emulator-5554
bash tests/E2E/scripts/install-tasks.sh install-release
bash tests/E2E/scripts/install-tasks.sh status
bash tests/E2E/scripts/install-tasks.sh restart
```

The installer checks device identity and boot completion, installs with `adb
install -r`, and checks launch and process existence. Reinstallation preserves
app data. A signature mismatch fails; the script never uninstalls to work around
it. Use a separate clean AVD named `tasks-testrigor-e2e-source` for a source
debug APK, select its serial and pass `TASKS_SOURCE_APK` to `install-source`.
The installer checks the AVD name for each signing identity.

`logs` prints the current app process's logcat output. Treat logs as private and
review them before sharing. `reset --confirm-reset` clears all app-local data,
including tasks, settings and account sessions, and relaunches first-run setup.
It preserves the APK, SDK, AVD and private evidence; it does not delete server
data. Run it only on the disposable AVD. `restart` preserves app data.

Before calling Phase 2 complete, exercise repeat installation, restart and reset;
inspect first-run behavior and persisted task state on the actual device; verify
APK package/version/signing identity; and build the pinned source revision.
Shell syntax and checksum checks establish neither rendered UI nor cloud device
execution. testRigor cloud runs and remote changes require their own approved
scope. No suite ID, token or device-specific connection belongs in this repo.

## testRigor cloud launch configuration

For the Android suite, configure these Appium capabilities before running:

```json
{
  "appium:appActivity": "com.todoroo.astrid.activity.TaskListActivity",
  "appium:appWaitActivity": "com.todoroo.astrid.activity.MainActivity"
}
```

`TaskListActivity` is the exported launcher activity alias; it targets
`MainActivity`. Launch through the alias and wait for the target activity.
Without these explicit settings, the initial cloud attempt failed before any
test steps with `Application failed to start`. The suite owner resolved startup
by setting both capabilities. Retain them when recreating the suite; local
direct-activity launch checks alone do not verify cloud startup behavior.

With these capabilities, TC-01 passed five consecutive full cloud runs on
2026-11-26 using testRigor CLI `3.0.0`, retries disabled, and the Android 36 /
Pixel 9 x86_64 suite. All five used the same source-built APK from
`e9472b806434ddba2263ce4108730f7010cd5d32` (SHA-256
`8b2f9aff137022b3a7542b1b83c0d477fa1a4a7b7d9f4053250523bd2c187727`)
and unchanged case/harness. The case creates a unique offline task, checks its
persistence after restart, deletes it, and checks absence after another restart.
Each run had a clean CLI exit and a JUnit report with one test and no failures,
errors or skips. This cloud verification covers the source debug build.
Published release cloud execution remains unverified; expanded native offline
coverage is documented below.

Branch runs keep mutations separate from the saved baseline, even with
`--explicit-mutations`; see testRigor's [baseline and branch mutation behavior](https://testrigor.com/blog/february-13-2023-release-notes-reusable-rules-via-api/).
Omit `--branch` / `--commit` for baseline updates and record the tested source SHA
separately. On the verified CLI `3.0.0` mobile upload path, even the baseline run
with `--explicit-mutations` left saved definitions unchanged. Saving TC-01
required a separate MCP `create_test_case` operation with `retest: false`.
Back up existing content and compare the saved steps and labels with local files
after any synchronization; a passing execution alone does not establish that
definitions were saved.

## Native offline coverage

TC-01 has the Phase 3 evidence above. TC-02 through TC-10 are Phase 4 development
cases; syntax validation alone does not establish successful device execution.
On 2026-11-27, the suite owner temporarily reduced the Phase 4 acceptance target
to one clean full-suite run while the native restart termination issue remains
unresolved. The application, cases, rules, harness and environment must remain
fixed for the accepted run. This reduced acceptance target does not establish
sustained reliability or confirm that the termination issue has been fixed.

The expanded ten-case suite has one observed full cloud pass. That run's CLI
polling failed, so it does not meet the clean-run acceptance requirement.
Subsequent execution hit intermittent
`restart app` termination errors reporting `RUNNING_IN_BACKGROUND` when
`NOT_RUNNING` was expected. Preserve the failed run and investigate native
restart handling before claiming expanded-suite reliability. The case restart
assertions remain part of the required coverage.

A subsequent full run with parallel execution disabled
(`useParallelCombinator=false`) finished with nine passes and one failure:
TC-09 reproduced the same `RUNNING_IN_BACKGROUND` termination error at
`restart app`. This setting change did not eliminate the error. The CLI also
lost its polling connection; the recovered JUnit report and completed cloud
results both show ten tests and one failure. No case, rule or APK changes were
made for this retry.

On 2026-11-27, all ten cases passed together in a subsequent full cloud run with
CLI exit 0 and JUnit showing ten tests, zero failures, zero errors and zero
skips. Every case's restart and final cleanup traces were independently audited.
This meets the owner's temporary one-pass acceptance target. The native
termination issue remains unresolved; one passing run does not establish that
it has been fixed or demonstrate sustained reliability. The run used the same
source APK, cases, rules and harness, parallel execution disabled, zero retries
and one configured node. The current settings export additionally contained
`ignoreMinimizedWindows=false`, which was absent from the earlier export; this
field was recorded in the new baseline without changing remote settings.

| Case | Behavior checked |
| --- | --- |
| TC-01 | Create, persist and delete a task across restarts |
| TC-02 | Replace a saved title and description and verify both after restart |
| TC-03 | Discard edits and retain the original saved values after restart |
| TC-04 | Cancel deletion, preserve the task, then confirm deletion |
| TC-05 | Save and clear a due date across separate restarts |
| TC-06 | Persist priority changes across separate restarts |
| TC-07 | Complete and reopen a task, checking saved completion metadata |
| TC-08 | Search among two unique tasks and restore the unfiltered list |
| TC-09 | Save and remove daily recurrence across separate restarts |
| TC-10 | Persist a parent-child relationship and an edited subtask |

The new cases share four rules. `offline-open-task-list` handles optional
onboarding; `offline-create-unique-task` creates an owned task;
`offline-create-described-task` creates an owned task with notes. The create
rules expose `taskTitle`, and the described variant also exposes `taskNotes`.
`offline-delete-current-task` requires the caller to have opened its own task
editor; the caller verifies absence afterward. Nested rules carry the same
`phase4-offline` label as their callers. TC-01 remains independent of these rules.

TC-07 uses visual AI clicks for the custom completion checkbox, which has no
accessible caption and could not be found with ordinary image/checkbox
references. Each click is anchored to the generated task title. Saved completion
metadata is checked independently after restart, and the case expands the
collapsed `Completed` section when needed to reopen the task.

Every case generates unique task data and deletes it on success. Search owns
two tasks; the subtask case owns its parent and child. After a failure, inspect
the run evidence and clean only the generated data before retrying. Use one
configured test node while establishing sequential reliability; do not overlap
runs on the same suite, because the CLI can cancel the previous run.

For an authorized development run with CLI `3.0.0`, provide the designated suite,
source-built APK, branch and the APK's source SHA. Keep the authentication token
in the process environment as `TESTRIGOR_API_KEY`. Use an existing private output
directory and a unique `TASKS_E2E_JUNIT` filename for every run:

```bash
testrigor test-suite run "$TESTRIGOR_SUITE_ID" \
  --file-path "$TASKS_E2E_APK" \
  --test-cases-path "tests/E2E/test-cases/*.yaml" \
  --rules-path "tests/E2E/rules/*.yaml" \
  --branch "$TASKS_E2E_BRANCH" --commit "$TASKS_E2E_SOURCE_SHA" \
  --junit-report-save-path "$TASKS_E2E_JUNIT"
```

Use forward slashes in glob patterns on Windows too: backslash globs can match
zero files. Verify the CLI loaded the intended cases and every nested rule.
Preserve its exit code, actual run ID and JUnit result. On the verified mobile
upload path, a queued-run response can omit the task ID and the CLI can skip
JUnit generation; retrieve the report for the actual run ID before calling
the evidence complete. Saved-suite persistence is a separate verified operation
as described above.

## Verified local environment

Local verification used WSL Ubuntu 24.04, Temurin JDK `25.0.5.1+2`, the pinned
Gradle wrapper `9.8.1`, Android Emulator `37.3.10`, platform-tools `37.0.3`,
and the Android 36 Google APIs x86_64 system image revision 7. Two separate
generic AVDs used a 320x640 display, 2 GB RAM and two CPU cores each, with KVM
and headless software rendering. This matches the cloud suite's API and ABI;
the local device profile is not a Pixel 9. Local checks are not testRigor runs.

For both the published release and the source debug build, first-run
`Continue without sync` reached the offline task list. A unique task survived
restart and repeat installation. Reset returned to onboarding; after continuing
without sync again, the task was absent and the list was empty. An initial
single UI probe ran before a transition completed; subsequent verification used
conditional readiness checks. These local setup probes are separate from the
cloud reliability evidence above.

## Cleanup after every local session

Inventory existing resources first. Put toolchains, Gradle caches, SDK state and
AVDs in a unique private temporary workspace. Use an isolated adb server port
and explicit device serials. After collecting evidence, stop the session's AVDs,
adb servers and build processes, and remove its toolchain, caches and device
images. Inspect actual Android home directories too: some tools create SDK
analytics or emulator/adb caches outside the configured state directory. Remove
only files attributable to the session; preserve prior user files.

Retain the APKs, sanitized logs, screenshots, package metadata and file hashes
in the private project artifacts. On this workstation, stop Ubuntu WSL once
the task is finished and it has no unrelated work. Do not stop other
distributions. The verified temporary environment is removed after use and must
be provisioned again before another local run.
