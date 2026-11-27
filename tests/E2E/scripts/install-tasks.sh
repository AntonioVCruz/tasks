#!/usr/bin/env bash
set -euo pipefail

# Keep APKs, build caches and evidence in the private project workspace.
: "${TASKS_E2E_STATE_DIR:?Set TASKS_E2E_STATE_DIR to an absolute private artifacts/runtime path}"
[[ "$TASKS_E2E_STATE_DIR" = /* ]] || { echo 'State directory must be absolute.' >&2; exit 2; }
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd -P)
mkdir -p -- "$TASKS_E2E_STATE_DIR"
state=$(cd -- "$TASKS_E2E_STATE_DIR" && pwd -P)
case "$state/" in "$repo/"*) echo 'State directory must be outside the repository.' >&2; exit 2;; esac
version=15.14.1
checksum=0823d18f54d50bb39bc462f5afdbaecab7e2594ee10564032e0152aa14528de8
apk="$state/releases/$version/tasks-googleplay-$version.apk"
url="https://github.com/tasks/tasks/releases/download/$version/tasks-googleplay-$version.apk"
package=org.tasks
activity=com.todoroo.astrid.activity.MainActivity

verify() {
    printf '%s  %s\n' "$checksum" "$apk" | sha256sum --check --status
    printf 'Verified release APK: %s\n' "$apk"
}

download() {
    if [[ -f "$apk" ]]; then verify; return; fi
    mkdir -p -- "$(dirname -- "$apk")"
    local partial
    partial=$(mktemp "$apk.partial.XXXXXX")
    # Preserve a failed download for diagnosis; never replace an existing APK.
    curl --fail --location --retry 2 --output "$partial" "$url"
    printf '%s  %s\n' "$checksum" "$partial" | sha256sum --check --status
    [[ ! -e "$apk" ]] || { echo 'APK appeared during download; preserved both files.' >&2; exit 1; }
    mv -- "$partial" "$apk"
    verify
}

device() {
    : "${TASKS_ANDROID_SERIAL:?Select the dedicated emulator explicitly}"
    command -v adb >/dev/null || { echo 'Android SDK platform-tools/adb is required.' >&2; exit 2; }
    [[ "$TASKS_ANDROID_SERIAL" = emulator-* ]] || { echo 'Only a dedicated emulator is supported.' >&2; exit 2; }
    [[ "$(adb -s "$TASKS_ANDROID_SERIAL" get-state)" = device ]]
    local avd
    avd=$(adb -s "$TASKS_ANDROID_SERIAL" emu avd name | tr -d '\r' | head -n 1)
    case "$avd" in
        tasks-testrigor-e2e|tasks-testrigor-e2e-source) ;;
        *) echo 'Use a dedicated tasks-testrigor-e2e or tasks-testrigor-e2e-source AVD.' >&2; exit 2;;
    esac
    if [[ "${1:-}" = release && "$avd" != tasks-testrigor-e2e ]] ||
       [[ "${1:-}" = source && "$avd" != tasks-testrigor-e2e-source ]]; then
        echo 'Select the separate AVD for this signing identity.' >&2; exit 2
    fi
    [[ "$(adb -s "$TASKS_ANDROID_SERIAL" shell getprop sys.boot_completed | tr -d '\r')" = 1 ]] || {
        echo 'Emulator has not completed boot.' >&2; exit 1;
    }
}

launch() {
    adb -s "$TASKS_ANDROID_SERIAL" shell am start -W -n "$package/$activity"
    adb -s "$TASKS_ANDROID_SERIAL" shell pidof "$package" >/dev/null
    echo 'Launch/process check passed; rendered UI is not verified by this check.'
}

case "${1:-help}" in
    download) download ;;
    verify) verify ;;
    build)
        command -v java >/dev/null || { echo 'JDK 25 is required; see repository CI.' >&2; exit 2; }
        : "${ANDROID_HOME:?Set ANDROID_HOME to an Android SDK with platform 37 and accepted licenses}"
        export GRADLE_USER_HOME="$state/gradle-user-home"
        cd -- "$repo"
        bash ./gradlew :app:assembleGoogleplayDebug --no-daemon --console=plain --stacktrace --info
        source_apk="$repo/app/build/outputs/apk/googleplay/debug/app-googleplay-debug.apk"
        [[ -f "$source_apk" ]]
        mkdir -p -- "$state/source-builds"
        source_copy="$state/source-builds/$(date -u +%Y%m%dT%H%M%SZ)-$(git rev-parse --short HEAD)-googleplay-debug.apk"
        [[ ! -e "$source_copy" ]]
        cp -- "$source_apk" "$source_copy"
        sha256sum "$source_copy"
        echo 'Source debug build has a different signing key from the published release; use a separate AVD.'
        ;;
    install-release)
        device release
        download
        # -r preserves app data; signature conflicts fail rather than uninstalling.
        adb -s "$TASKS_ANDROID_SERIAL" install -r "$apk"
        launch
        ;;
    install-source)
        device source
        : "${TASKS_SOURCE_APK:?Set TASKS_SOURCE_APK to the APK produced by the build command}"
        [[ -f "$TASKS_SOURCE_APK" ]]
        adb -s "$TASKS_ANDROID_SERIAL" install -r "$TASKS_SOURCE_APK"
        launch
        ;;
    status)
        device
        adb -s "$TASKS_ANDROID_SERIAL" shell pm path "$package"
        adb -s "$TASKS_ANDROID_SERIAL" shell dumpsys package "$package" | sed -n '/versionCode=/p; /versionName=/p'
        ;;
    logs)
        device
        app_pid=$(adb -s "$TASKS_ANDROID_SERIAL" shell pidof -s "$package" | tr -d '\r')
        [[ -n "$app_pid" ]]
        adb -s "$TASKS_ANDROID_SERIAL" logcat -d --pid="$app_pid"
        ;;
    restart)
        device
        adb -s "$TASKS_ANDROID_SERIAL" shell am force-stop "$package"
        launch
        ;;
    reset)
        [[ "${2:-}" = --confirm-reset ]] || { echo 'Reset requires --confirm-reset and erases app data on the dedicated AVD.' >&2; exit 2; }
        device
        adb -s "$TASKS_ANDROID_SERIAL" shell pm clear "$package"
        launch
        ;;
    help|--help|-h)
        echo 'Usage: install-tasks.sh download|verify|build|install-release|install-source|status|logs|restart|reset --confirm-reset'
        ;;
    *) echo 'Unknown command.' >&2; exit 2 ;;
esac
