"""Offline checks for the CI gate's evidence and failure handling; no cloud calls."""

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

spec = importlib.util.spec_from_file_location('tasks_ci', Path(__file__).with_name('ci.py'))
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)
SHA = 'f' * 40


def report(path, **changes):
    identities = {'testSuiteId': 'Suite123', 'taskId': 'Run123', 'branchName': 'ci-42-1', 'commit': SHA}
    identities.update(changes)
    root = ET.Element('testsuites', time='1500')
    suite = ET.SubElement(root, 'testsuite')
    for p in sorted((ci.REPO / 'tests/E2E/test-cases').glob('*.yaml')):
        ET.SubElement(suite, 'testcase', name=p.stem, status='success')
    properties = ET.SubElement(suite, 'properties')
    for name, value in identities.items():
        ET.SubElement(properties, 'properties', name=name, value=value)
    ET.ElementTree(root).write(path, encoding='utf-8')


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.xml = self.root / 'report.xml'
        report(self.xml)

    def validate(self):
        return ci.validate_report(self.xml, 'Suite123', 'Run123', 'ci-42-1', SHA)

    def test_accepts_exact_full_report(self):
        self.assertEqual(self.validate()['tests'], 10)

    def test_rejects_stale_run_and_wrong_source(self):
        for key in ['taskId', 'testSuiteId', 'branchName', 'commit']:
            with self.subTest(key=key):
                report(self.xml, **{key: 'another-value'})
                with self.assertRaises(ValueError):
                    self.validate()

    def test_rejects_failure_error_skip_and_incomplete_report(self):
        for tag in ['failure', 'error', 'skipped']:
            with self.subTest(tag=tag):
                report(self.xml)
                tree = ET.parse(self.xml)
                ET.SubElement(tree.find('.//testcase'), tag)
                tree.write(self.xml)
                with self.assertRaises(ValueError):
                    self.validate()
        tree = ET.parse(self.xml)
        suite = tree.find('testsuite')
        suite.remove(suite.find('testcase'))
        tree.write(self.xml)
        with self.assertRaises(ValueError):
            self.validate()

    def test_rejects_duplicate_case_even_with_ten_results(self):
        tree = ET.parse(self.xml)
        cases = tree.findall('.//testcase')
        cases[1].set('name', cases[0].get('name'))
        tree.write(self.xml)
        with self.assertRaises(ValueError):
            self.validate()

    def test_rejects_tampered_apk_and_harness(self):
        apk = self.root / 'source.apk'
        with zipfile.ZipFile(apk, 'w') as archive:
            archive.writestr('AndroidManifest.xml', 'fixture')
        package = self.root / 'package'
        with patch.object(ci, 'revision', return_value=SHA):
            ci.prepare(apk, package)
            self.assertEqual(ci.verify_package(package)['source_sha'], SHA)
            (package / 'app.apk').write_bytes(b'tampered')
            with self.assertRaises(ValueError):
                ci.verify_package(package)
            (package / 'app.apk').write_bytes(apk.read_bytes())
            with patch.object(ci, 'harness_hashes', return_value={'changed': 'hash'}):
                with self.assertRaises(ValueError):
                    ci.verify_package(package)

    def test_credentials_only_go_to_fixed_host(self):
        self.assertIsNone(ci.run_id('https://other.example/suites/Suite123/runs/Run123', 'Suite123'))
        self.assertIsNone(ci.run_id('https://app.testrigor.com/suites/Other/runs/Run123', 'Suite123'))
        self.assertEqual(ci.run_id('https://app.testrigor.com/suites/Suite123/runs/Run123', 'Suite123'), 'Run123')

    def test_access_error_explains_rejection_without_printing_token(self):
        data = json.dumps({'message': 'Rejected fake-ci-token'}).encode()
        with patch.object(ci, 'request', return_value=(403, 'application/json', data)):
            with self.assertRaisesRegex(ValueError, 'HTTP 403') as error:
                ci.status('Suite123', 'main', 'fake-ci-token')
        self.assertNotIn('fake-ci-token', str(error.exception))
        self.assertIn('[REDACTED]', str(error.exception))


class RunnerTests(unittest.TestCase):
    def simulate(self, cli_exit=0, terminal_code=200, report_run='Run123', preflight_code=200):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / 'results'
            child = type('Child', (), {'stdout': ['mock fake-ci-token output\n'], 'wait': lambda self: cli_exit})()
            def retrieve(suite, run, token, target):
                report(target, taskId=report_run)
            captured = io.StringIO()
            with contextlib.ExitStack() as stack:
                stack.enter_context(patch.dict(os.environ, {'TESTRIGOR_API_KEY': 'fake-ci-token', 'TESTRIGOR_SUITE_ID': 'Suite123', 'TASKS_E2E_BRANCH': 'ci-42-1'}))
                stack.enter_context(patch.object(ci, 'verify_package', return_value={'source_sha': SHA}))
                stack.enter_context(patch.object(ci.shutil, 'which', return_value='testrigor'))
                stack.enter_context(patch.object(ci.subprocess, 'check_output', return_value='@testrigor/testrigor-cli/3.0.0 linux-x64 node-v22.15.0'))
                popen = stack.enter_context(patch.object(ci.subprocess, 'Popen', return_value=child))
                stack.enter_context(patch.object(ci, 'status', side_effect=[(preflight_code, 'OldRun'), (terminal_code, 'Run123')]))
                fetch = stack.enter_context(patch.object(ci, 'retrieve_report', side_effect=retrieve))
                stack.enter_context(contextlib.redirect_stdout(captured))
                stack.enter_context(contextlib.redirect_stderr(captured))
                if preflight_code == 228:
                    with self.assertRaises(ValueError):
                        ci.run(root, output)
                    self.assertEqual(popen.call_count, 0)
                    return
                result = ci.run(root, output)
            summary = json.loads((output / 'result.json').read_text())
            log = (output / 'cli.log').read_text()
            self.assertNotIn('fake-ci-token', log + captured.getvalue())
            self.assertEqual(popen.call_count, 1)  # No execution retry, including on failures.
            self.assertEqual(fetch.call_args.args[1], 'Run123')
            command = popen.call_args.args[0]
            self.assertNotIn('--explicit-mutations', command)
            self.assertNotIn('--auth-token', command)
            self.assertNotIn('fake-ci-token', command)
            return result, summary

    def test_recovers_mobile_junit_and_accepts_clean_cli(self):
        code, summary = self.simulate()
        self.assertEqual(code, 0)
        self.assertTrue(summary['accepted'])

    def test_preserves_cli_failure_even_if_cloud_passes(self):
        code, summary = self.simulate(cli_exit=7)
        self.assertEqual(code, 7)
        self.assertFalse(summary['accepted'])

    def test_rejects_failed_cloud_status_even_with_successful_cli(self):
        code, summary = self.simulate(terminal_code=230)
        self.assertEqual(code, 1)
        self.assertFalse(summary['accepted'])

    def test_rejects_stale_junit_after_clean_cli(self):
        code, summary = self.simulate(report_run='OldRun')
        self.assertEqual(code, 1)
        self.assertFalse(summary['accepted'])

    def test_active_branch_prevents_submission(self):
        self.simulate(preflight_code=228)


if __name__ == '__main__':
    unittest.main()
