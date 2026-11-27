#!/usr/bin/env python3
"""Build provenance and one cloud execution; no suite sync or execution retries."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

REPO = Path(__file__).resolve().parents[3]
CLI_VERSION = '3.0.0'


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def revision():
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip()
    if head != os.environ.get('TASKS_SOURCE_SHA'):
        raise ValueError('Checked-out revision does not match TASKS_SOURCE_SHA')
    return head


def harness_hashes():
    paths = sorted((REPO / 'tests/E2E').rglob('*.yaml')) + [Path(__file__), REPO / 'tests/E2E/scripts/install-tasks.sh']
    return {p.relative_to(REPO).as_posix(): sha256(p) for p in paths}


def prepare(apk, output):
    head = revision()
    with zipfile.ZipFile(apk) as archive:
        if 'AndroidManifest.xml' not in archive.namelist():
            raise ValueError('Build output is not an APK')
    output.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(apk, output / 'app.apk')
    write_json(output / 'provenance.json', {
        'source_sha': head, 'harness_sha': head,
        'apk_sha256': sha256(output / 'app.apk'),
        'variant': 'googleplayDebug', 'harness_files': harness_hashes(),
    })


def verify_package(package):
    head = revision()
    provenance = json.loads((package / 'provenance.json').read_text(encoding='utf-8'))
    if (provenance['source_sha'] != head or provenance['harness_sha'] != head
            or provenance['variant'] != 'googleplayDebug'
            or provenance['apk_sha256'] != sha256(package / 'app.apk')
            or provenance['harness_files'] != harness_hashes()):
        raise ValueError('APK/source/harness provenance mismatch')
    return provenance


def request(url, token):
    req = urllib.request.Request(url, headers={'auth-token': token, 'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status, response.headers.get_content_type(), response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.headers.get_content_type(), error.read()


def run_id(url, suite):
    match = re.fullmatch(r'https://app\.testrigor\.com/(?:suites|test-suites)/' + re.escape(suite) + r'/runs/([A-Za-z0-9]+)', url or '')
    return match[1] if match else None


def status(suite, branch, token):
    url = 'https://app.testrigor.com/api/v1/apps/' + suite + '/status?'
    code, content_type, data = request(url + urllib.parse.urlencode({'branchName': branch}), token)
    if code == 404:
        return code, None  # A new CI branch may have no previous run.
    if code not in [200, 227, 228, 229, 230]:
        detail = content_type
        try:
            body = json.loads(data)
            if isinstance(body, dict):
                detail += ': ' + str(body.get('message', body.get('error', 'no error message')))
        except (ValueError, UnicodeDecodeError):
            if b'cloudflare' in data.lower():
                detail += ': Cloudflare response'
        raise ValueError(f'Suite status request failed: HTTP {code}; {detail.replace(token, "[REDACTED]")[:240]}')
    body = json.loads(data)
    return code, run_id(body.get('detailsUrl'), suite)


def check_access():
    token = os.environ.get('TESTRIGOR_API_KEY', '')
    suite = os.environ.get('TESTRIGOR_SUITE_ID', '')
    branch = os.environ.get('TASKS_E2E_BRANCH', '')
    if not token or not re.fullmatch(r'[A-Za-z0-9_-]+', suite) or not re.fullmatch(r'ci-[0-9]+-[0-9]+', branch):
        raise ValueError('Missing or invalid access-check configuration')
    failed = False
    for kind, name in [('baseline', os.environ.get('TASKS_DEFAULT_BRANCH', 'main')), ('ci', branch)]:
        try:
            code, _ = status(suite, name, token)
            print(json.dumps({'branch_kind': kind, 'status_http': code}))
            failed |= code not in [200, 229, 230, 404]
        except (ValueError, OSError) as error:
            print(json.dumps({'branch_kind': kind, 'error': str(error).replace(token, '[REDACTED]')}))
            failed = True
    return 1 if failed else 0


def retrieve_report(suite, run, token, target):
    """CLI 3.0.0's queued mobile response can omit the JUnit task ID."""
    url = f'https://api2.testrigor.com/api/v1/apps/{suite}/runs/{run}/junit_report'
    for _ in range(12):
        code, content_type, data = request(url, token)
        if code == 200:
            if content_type != 'application/xml':
                raise ValueError('JUnit endpoint did not return XML')
            target.write_bytes(data)
            return
        if code != 228:
            raise ValueError(f'JUnit report request failed: HTTP {code}')
        time.sleep(5)
    raise ValueError('JUnit generation did not finish; inspect the existing run')


def validate_report(report, suite, run, branch, commit):
    root = ET.parse(report).getroot()
    cases = root.findall('.//testcase')
    expected = len(list((REPO / 'tests/E2E/test-cases').glob('*.yaml')))
    identities = {p.get('name'): p.get('value') for p in root.findall('.//properties[@name]')}
    if any(identities.get(k) != v for k, v in {
        'testSuiteId': suite, 'taskId': run, 'branchName': branch, 'commit': commit,
    }.items()):
        raise ValueError('JUnit does not identify this suite/run/branch/source')
    if len(cases) != expected or expected != 10:
        raise ValueError('JUnit does not contain the expected ten cases')
    names = {p.stem for p in (REPO / 'tests/E2E/test-cases').glob('*.yaml')}
    if {c.get('name') for c in cases} != names:
        raise ValueError('JUnit does not contain the expected case identities')
    if any(root.findall('.//' + tag) for tag in ['failure', 'error', 'skipped']):
        raise ValueError('JUnit contains failures, errors or skipped cases')
    if any(c.get('status') != 'success' for c in cases):
        raise ValueError('JUnit contains a case without a successful status')
    return {'tests': len(cases), 'failures': 0, 'errors': 0, 'skipped': 0,
            'junit_duration_seconds': root.get('time')}


def run(package, output):
    # All integrity/config checks precede any execution request.
    provenance = verify_package(package)
    token = os.environ.get('TESTRIGOR_API_KEY', '')
    suite = os.environ.get('TESTRIGOR_SUITE_ID', '')
    branch = os.environ.get('TASKS_E2E_BRANCH', '')
    if not token or not re.fullmatch(r'[A-Za-z0-9_-]+', suite) or not re.fullmatch(r'ci-[0-9]+-[0-9]+', branch):
        raise ValueError('Missing or invalid CI token, suite ID or run branch')
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / 'provenance.json', provenance)
    cli = shutil.which('testrigor')
    if not cli:
        raise ValueError('testRigor CLI is not installed')
    version = subprocess.check_output([cli, '--version'], text=True).strip()
    if not re.search(r'@testrigor/testrigor-cli/3\.0\.0(?:\s|$)', version):
        raise ValueError('Expected testRigor CLI ' + CLI_VERSION)
    write_json(output / 'runtime.json', {'cli': version, 'python': sys.version})
    code, previous = status(suite, branch, token)
    if code not in [200, 229, 230, 404]:
        raise ValueError('Suite status is not terminal; do not overlap cloud runs')
    report = output / 'report.xml'
    command = [cli, 'test-suite', 'run', suite,
               '--file-path', str(package / 'app.apk'),
               '--test-cases-path', (REPO / 'tests/E2E/test-cases/*.yaml').as_posix(),
               '--rules-path', (REPO / 'tests/E2E/rules/*.yaml').as_posix(),
               '--branch', branch, '--commit', provenance['source_sha'],
               '--junit-report-save-path', str(report)]
    started = time.time()
    summary = {'branch': branch, 'source_sha': provenance['source_sha'], 'cli_exit': None,
               'run_id': None, 'accepted': False, 'submission_started_unix': started}
    write_json(output / 'result.json', summary)
    with (output / 'cli.log').open('w', encoding='utf-8') as log:
        child = subprocess.Popen(command, cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, encoding='utf-8', errors='replace')
        for line in child.stdout:
            safe = line.replace(token, '[REDACTED]')
            log.write(safe)
            log.flush()
            print(safe, end='', flush=True)
        summary['cli_exit'] = child.wait()
    write_json(output / 'result.json', summary)
    # Recover only this submitted run. Never resubmit after a polling error.
    try:
        deadline = time.monotonic() + 600
        while True:
            code, current = status(suite, branch, token)
            if current and current != previous:
                summary['run_id'] = current
                summary['run_url'] = f'https://app.testrigor.com/suites/{suite}/runs/{current}'
            if code in [200, 229, 230] and summary['run_id']:
                break
            if time.monotonic() >= deadline:
                raise ValueError('Existing cloud run is active or unidentifiable; inspect it before another dispatch')
            time.sleep(10)
        summary['terminal_status_http'] = code
        # Fetch by the identified run ID even if CLI omitted or supplied a report.
        retrieve_report(suite, summary['run_id'], token, report)
        summary['junit'] = validate_report(report, suite, summary['run_id'], branch, provenance['source_sha'])
        summary['accepted'] = summary['cli_exit'] == 0 and code == 200
    except (ValueError, OSError, ET.ParseError) as error:
        summary['evidence_error'] = str(error).replace(token, '[REDACTED]')
    finally:
        summary['local_evidence_finished_unix'] = time.time()
        write_json(output / 'result.json', summary)
    if not summary['accepted']:
        print('E2E failed; inspect result.json, cli.log and the identified cloud run. No retry was submitted.', file=sys.stderr)
        return summary['cli_exit'] if summary['cli_exit'] and summary['cli_exit'] > 0 else 1
    print('All ten native offline cases passed with a clean CLI exit and matching JUnit.')
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    build = commands.add_parser('prepare')
    build.add_argument('--apk', type=Path, required=True)
    build.add_argument('--output', type=Path, required=True)
    cloud = commands.add_parser('run')
    cloud.add_argument('--package', type=Path, required=True)
    cloud.add_argument('--output', type=Path, required=True)
    commands.add_parser('check-access')
    args = parser.parse_args()
    try:
        if args.command == 'prepare':
            prepare(args.apk, args.output)
            return 0
        if args.command == 'check-access':
            return check_access()
        return run(args.package, args.output)
    except (ValueError, OSError, KeyError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        token = os.environ.get('TESTRIGOR_API_KEY', '')
        message = str(error)
        print(message.replace(token, '[REDACTED]') if token else message, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
