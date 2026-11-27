# Native Android E2E tests

These testRigor cases cover offline task behavior in the Google Play Android
application. They use generated task data, verify persistence after application
restarts, and delete their generated tasks on success.

| Case | Behavior |
| --- | --- |
| TC-01 | Create, persist and delete a task |
| TC-02 | Edit a saved title and description |
| TC-03 | Discard edits and retain saved values |
| TC-04 | Cancel deletion, then confirm deletion |
| TC-05 | Save and clear a due date |
| TC-06 | Persist priority changes |
| TC-07 | Complete and reopen a task |
| TC-08 | Search among tasks and restore the unfiltered list |
| TC-09 | Save and remove daily recurrence |
| TC-10 | Persist a parent-child relationship and edit a subtask |

The four files in `rules/` share onboarding, task creation and deletion steps.
The create rules expose `taskTitle`; the described-task variant also exposes
`taskNotes`. The delete rule requires an open task editor. Callers verify that
deletion persists. TC-01 is a standalone smoke case.

TC-07 locates the completion checkbox visually, anchored to its generated task
title, and verifies saved completion metadata after restart.

## Requirements

- A testRigor native Android suite with Android 36 / Pixel 9 x86_64.
- One execution node, zero retries, and parallel combinator disabled.
- `ignoreMinimizedWindows=false` and these Appium launch capabilities:

```json
{
  "appium:appActivity": "com.todoroo.astrid.activity.TaskListActivity",
  "appium:appWaitActivity": "com.todoroo.astrid.activity.MainActivity"
}
```

`TaskListActivity` is the exported launcher alias for `MainActivity`. The cases
accept either initial onboarding or an existing offline task list. Use a
dedicated suite/device and keep its language set to English. Account sync,
billing and map services are outside this coverage.

## Build and run

Install JDK 25 and Android SDK platform `android-37.0`, accept SDK licenses, and
set `ANDROID_HOME`. See [CONTRIBUTING.md](../../CONTRIBUTING.md) for application
development setup. The debug build needs no production signing key.

```bash
export TASKS_E2E_STATE_DIR=/absolute/path/outside/checkout/tasks-e2e
bash tests/E2E/scripts/build-apk.sh build
npm install --global @testrigor/testrigor-cli@3.0.0

# Supply the suite credential through TESTRIGOR_API_KEY in the process environment.
# Set TESTRIGOR_SUITE_ID and choose a unique TASKS_E2E_BRANCH for this execution.
testrigor test-suite run "$TESTRIGOR_SUITE_ID" \
  --file-path app/build/outputs/apk/googleplay/debug/app-googleplay-debug.apk \
  --test-cases-path "tests/E2E/test-cases/*.yaml" \
  --rules-path "tests/E2E/rules/*.yaml" \
  --branch "$TASKS_E2E_BRANCH" --commit "$(git rev-parse HEAD)" \
  --junit-report-save-path "$TASKS_E2E_STATE_DIR/report.xml"
```

Use forward slashes in CLI glob patterns on Windows. Choose a new report path
for each run and preserve the CLI exit status. CLI 3.0.0 can omit JUnit after a
queued mobile upload; the [CI runner](CI.md) retrieves the identified run's report.
Branch submissions execute the supplied definitions without synchronizing the
saved suite. They do not use authoritative mutations or settings overrides.

Do not overlap executions on the same suite: a CLI submission can cancel an
existing run. After a failure, inspect the run and clean only its generated data.
Keep APKs, credentials and execution artifacts outside the checkout.

See [CI.md](CI.md) for the optional GitHub Actions workflow and offline checks.
