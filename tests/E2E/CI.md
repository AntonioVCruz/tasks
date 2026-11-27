# Optional native Android E2E workflow

`.github/workflows/e2e-tests.yml` builds a Google Play debug APK from the checked-out
source, uploads it to testRigor and executes the ten offline cases. It runs only
by manual dispatch from the default branch and requires explicit configuration.
It is advisory and does not add a required branch check.

## Configuration

Create a dedicated native Android suite using the [README requirements](README.md#requirements).
Choose a suite owner, credential holder and triage owner. Configure these repository
settings, enabling the workflow after the suite and credential are ready:

| Setting | Value |
| --- | --- |
| Variable `TESTRIGOR_SUITE_ID` | Native Android suite ID |
| Secret `TESTRIGOR_CI_TOKEN` | The suite's CI/CD integration token |
| Variable `TESTRIGOR_E2E_ENABLED` | Exactly `true` |

The workflow maps the CI secret to `TESTRIGOR_API_KEY` only for access checks and
test execution. No personal token file or global authentication is used. Missing
configuration skips the downstream jobs. Run the workflow from the Actions tab
after installing it on the default branch.

The suite receives the APK and generated test data through testRigor's service.
Review service access and artifact visibility with the suite owner before use.

## Execution and results

The gate checks opt-in, credentials and the default branch without checkout.
An access job verifies suite access before the build. The build uses JDK 25,
the checked-in Gradle wrapper and Android SDK platform `android-37.0`, without
testRigor credentials or production signing keys. Third-party actions are pinned
to commit SHAs; the E2E job installs testRigor CLI `3.0.0` with Node 22.

The build packages the APK with source/harness revisions and SHA-256 digests.
The E2E job verifies those identities before submitting the ten cases and four
rules once on a unique `ci-<run-id>-<attempt>` branch. It does not synchronize
saved definitions, override suite settings or retry execution.

The Python standard-library runner retrieves JUnit for the newly identified run,
including when CLI 3.0.0 omits the report after a queued mobile response. Success
requires CLI exit 0, successful terminal status, the ten expected case names,
matching suite/run/branch/commit metadata, and no failed, errored or skipped cases.
Polling or report retrieval never resubmits tests; missing evidence fails the job.

| Resource | Limit |
| --- | --- |
| Gate and access jobs | 5 minutes each |
| Source build | 35 minutes |
| E2E job | 75 minutes |
| APK, provenance and failed-build log | Retained 3 days |
| CLI log, result JSON, provenance and JUnit | Retained 7 days |

Suite-specific concurrency queues workflow runs without cancelling an active run.
Other workflows using the same suite must share that concurrency group; local
executions and other repositories need separate coordination. A timeout or polling
failure may leave a cloud execution active. Inspect its status before dispatching
again.

For triage, inspect `result.json`, the sanitized `cli.log`, JUnit and the identified
cloud run. Compare APK/source/harness identities. Rotate the suite CI token when
access changes and validate the replacement with the suite owner. To disable the
workflow, set `TESTRIGOR_E2E_ENABLED=false` and inspect any active execution.

## Offline checks

```bash
python3 tests/E2E/scripts/ci_test.py -v
bash -n tests/E2E/scripts/build-apk.sh
actionlint -shellcheck= -pyflakes= .github/workflows/e2e-tests.yml
```

The runner tests use mocks and make no cloud calls. They cover APK/harness
tampering, mismatched or incomplete reports, failed/skipped cases, credential
redaction, suite access, CLI failures and single-submission report recovery.
The actionlint command disables optional ShellCheck/Pyflakes integrations;
install those tools to enable their additional checks.

Reference: [testRigor CLI documentation](https://testrigor.com/command-line/).
