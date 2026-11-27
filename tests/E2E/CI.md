# Optional native Android E2E workflow

`.github/workflows/e2e-tests.yml` is a manual, disabled-by-default proposal. It
has been checked locally; **hosted execution and authentication with a suite CI
token remain unverified**. The source APK/upload/cloud-device route was exercised
in the development loop, but that does not verify the GitHub-hosted build.

## Repository-specific decisions

| Decision | Proposal and rationale |
| --- | --- |
| Trigger | Manual dispatch from the repository's default branch only. No scheduled, push, PR or `pull_request_target` execution. This keeps cloud use deliberate while the restart issue is open. |
| Opt-in | Require `TESTRIGOR_E2E_ENABLED=true`, a suite ID and a CI token. Missing configuration skips the build and E2E jobs cleanly. |
| Result | Advisory: do not add this job to required branch checks. A failed execution still fails the job; there is no `continue-on-error` or execution retry. |
| Application | Build `:app:assembleGoogleplayDebug` from the checked-out source through the existing installer, using JDK 25 and Android platform `android-37.0`. Production signing and map/provider keys are unnecessary for the covered offline flows. |
| Deployment | Upload the built APK to testRigor for installation on its native Android device. There is no browser server, VM deployment, tunnel or local emulator. The first case steps exercise actual cloud launch/onboarding. |
| Trust boundary | An access-check job verifies the suite token before building. A job with no testRigor credential builds the APK. A separate E2E job downloads that artifact, checks source/harness hashes and APK digest, then receives the CI token only on the run step. Checkouts do not retain the GitHub token. |
| Versions | Exact CLI `3.0.0`, the version exercised in development. Node 22 matches the verified major version. Third-party actions use full commit SHAs. JDK 25 and the checked-in Gradle wrapper follow this repository's CI conventions. |
| Duration | Gate 5 minutes, build 35 minutes, E2E 75 minutes; no job matrix. The accepted development cloud run took about 30 minutes. Hosted build/runtime limits are proposals until exercised. |
| Serialization | Stable `testrigor-<suite-id>` concurrency group, `cancel-in-progress: false`. Other workflows using this suite must use the same group. GitHub's default single pending slot may replace an unstarted pending dispatch; it does not cancel the active run. Local runs and other repositories are outside this lock. |
| Evidence | APK plus provenance retained 3 days; build failure log 3 days; sanitized CLI log, result JSON, provenance and JUnit 7 days. Artifact names include workflow run ID and attempt. No device/container logs are claimed. |
| Ownership | Before enabling upstream, maintainers must choose a suite owner, credential holder and triage owner. A dedicated CI suite is preferable to sharing a development suite, because CLI submissions can cancel another run. No upstream suite or owner has been selected. |

## Configuration and suite setup

An administrator of the repository that will run this workflow must supply:

- Repository variable `TESTRIGOR_SUITE_ID`: the intended native Android suite.
- Repository secret `TESTRIGOR_CI_TOKEN`: that suite's CI/CD integration token.
  The workflow maps this to `TESTRIGOR_API_KEY` on the run step. It neither reads
  a personal token file nor authenticates globally. A suite CI token cannot be
  used for MCP; the runner does not use MCP.
- Repository variable `TESTRIGOR_E2E_ENABLED`: exactly `true`, set last, after
  ownership, suite configuration, run budget and data visibility are agreed.

Configure the suite consistently with the exercised native environment:
Android 36 / Pixel 9 x86_64, one configured node, zero retries, parallel
combinator disabled, and the launch/wait capabilities in [README.md](README.md).
The current development export also contains `ignoreMinimizedWindows=false`.
The workflow does not change suite settings. Creating a dedicated CI suite,
copying accepted definitions or changing settings requires its own scope.

The initial hosted validation should authorize **one full cloud execution** on
an explicitly named suite, including the freshly built debug APK upload and
transient branch definitions. It must not overlap a local/manual run. The five
unused Phase 4 runs do not automatically authorize this separate CI validation.

Install the reviewed workflow and `tests/E2E/` files on the fork's default
branch before dispatching; the gate intentionally skips non-default refs.
Installing it on the upstream default branch requires maintainer acceptance.
Publishing commits, writing GitHub secrets/variables, enabling the workflow and
dispatching hosted validation have not been performed by the local preparation.

## What each dispatch does

The gate executes inline workflow code without checking out the repository.
When configured and enabled, the access job first requires a successful
unfiltered suite-status response, then checks the default and new CI branches.
A missing new branch is permitted; a missing suite is rejected. Requests use
the CLI's User-Agent and normalize surrounding credential whitespace. On failure it records bounded,
redacted error details and compares Node's HTTP client with Python's to help
distinguish a credential rejection from a client-specific response. No cloud
test is submitted by these checks. A failed access check skips the build.

After access succeeds, the build job runs the existing installer, then
`ci.py prepare` creates a package containing `app.apk` and a provenance manifest.
That manifest records the source and harness revisions, APK digest and hashes
of the local case/rule/runner files. No release APK is substituted for a failed
source build.

The E2E job installs CLI 3.0.0 and invokes `ci.py run`. It checks the downloaded
package against the current checkout and invokes the CLI **once**, uploading all
ten local cases and four rules on a unique `ci-<run-id>-<attempt>` branch. It
omits `--explicit-mutations` and settings overrides. Development observations
showed that this branch route keeps saved definitions separate; saved-suite
synchronization is not part of CI. Do not assume passing a run saves its files.

CLI 3.0.0 can omit JUnit when a queued mobile upload response lacks a task ID.
The wrapper identifies the new run through the same branch status route the CLI
uses, rejects the previous run ID, and retrieves that run's XML using the CI
token. These requests poll status/generate a report; they do not rerun tests.
If identification, authentication or report recovery fails, the job fails.
Success requires CLI exit 0, terminal successful status, exactly the ten expected
case names, successful case statuses, matching suite/run/branch/commit metadata,
and zero JUnit failures, errors or skips. A later successful report cannot turn
a failed CLI execution into a pass.

The Python runner uses only the standard library. Its status/JUnit fallback is
based on the inspected CLI 3.0.0 implementation and development report recovery.
The route's behavior with a suite CI token must still be verified in the first
approved hosted run. There is no fallback to a personal token.

## Triage, rotation and removal

The designated triage owner checks the uploaded `result.json`, `cli.log` and
JUnit, then the identified cloud run. Preserve the APK/source/harness identity
when comparing failures. The intermittent native `restart app` termination
error remains unresolved; do not suppress it, weaken restart checks or enable
test retries to obtain a green job. Phase 4 met a temporary one-pass acceptance
target, which does not establish sustained reliability.

Append future failed authorized runs to the private project investigation,
including cloud URL, result, affected case/flow IDs, exact failing steps/errors,
input changes and evidence. Record cloud execution duration separately from
JUnit duration and local polling/recovery time. Public artifacts should contain
only generated test data and sanitized diagnostics; confirm service data
visibility and artifact access before enabling upstream.

A workflow timeout, manual cancellation or polling failure can leave its cloud
run active. Before another dispatch, inspect that same cloud run and wait for a
terminal result. Do not launch a replacement to discover whether the previous
one is still running. GitHub concurrency does not coordinate local submissions
or submissions from a different repository.

The credential holder should revoke and replace the suite CI token when access
changes or compromise is suspected, then update `TESTRIGOR_CI_TOKEN` and perform
an approved validation. A periodic rotation interval remains an owner decision.
To disable the integration, set `TESTRIGOR_E2E_ENABLED=false`; then inspect any
active cloud execution. To remove it, remove the secret/variables and workflow,
and have the suite owner decide whether to retain the suite and evidence.

## Local validation

```bash
python3 tests/E2E/scripts/ci_test.py -v
python3 -m py_compile tests/E2E/scripts/ci.py
bash -n tests/E2E/scripts/install-tasks.sh
actionlint -shellcheck= -pyflakes= .github/workflows/e2e-tests.yml
```

The thirteen offline tests exercise APK/harness tamper detection, stale run/source/case
rejection, missing/failed/skipped results, CLI-exit preservation, credential
redaction, safe access-error diagnostics and the single-submission/report-recovery path using mocks. The gate's
inline script was also executed locally with missing configuration, non-default
refs, PR events and complete fake configuration. These checks do not execute the
GitHub service, build an APK or run cloud tests. ShellCheck/Pyflakes were not
available for this validation; actionlint's expression/schema checks and Bash
syntax checks were run explicitly.

References: [testRigor CLI](https://testrigor.com/command-line/),
[GitHub concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency),
[Android SDK action](https://github.com/android-actions/setup-android).
