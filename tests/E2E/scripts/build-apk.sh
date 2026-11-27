#!/usr/bin/env bash
set -euo pipefail

[[ "${1:-}" = build && "$#" = 1 ]] || {
    echo 'Usage: build-apk.sh build' >&2
    exit 2
}
: "${TASKS_E2E_STATE_DIR:?Set TASKS_E2E_STATE_DIR to an absolute directory outside the checkout}"
[[ "$TASKS_E2E_STATE_DIR" = /* ]] || { echo 'State directory must be absolute.' >&2; exit 2; }
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd -P)
mkdir -p -- "$TASKS_E2E_STATE_DIR"
state=$(cd -- "$TASKS_E2E_STATE_DIR" && pwd -P)
case "$state/" in "$repo/"*) echo 'State directory must be outside the repository.' >&2; exit 2;; esac
command -v java >/dev/null || { echo 'JDK 25 is required; see CONTRIBUTING.md.' >&2; exit 2; }
: "${ANDROID_HOME:?Set ANDROID_HOME to an Android SDK with platform android-37.0 and accepted licenses}"
export GRADLE_USER_HOME="$state/gradle-user-home"
cd -- "$repo"
bash ./gradlew :app:assembleGoogleplayDebug --no-daemon --console=plain --stacktrace --info
test -f app/build/outputs/apk/googleplay/debug/app-googleplay-debug.apk
