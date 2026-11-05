import importlib.util
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

spec = importlib.util.spec_from_file_location(
    'ci_report', Path(__file__).resolve().parents[1] / 'scripts' / 'check_test_report.py',
)
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


def test_report_accepts_successful_cases(tmp_path):
    path = tmp_path / 'report.xml'
    path.write_text('<testsuites><testsuite><testcase/><testcase/></testsuite></testsuites>')
    assert report.check_report(path) == 2


@pytest.mark.parametrize('xml', [
    '<testsuites/>',
    '<testsuite><testcase><skipped/></testcase></testsuite>',
    '<testsuite><testcase><failure/></testcase></testsuite>',
    '<testsuite><testcase><error/></testcase></testsuite>',
    '<testsuites><testsuite><testcase/></testsuite><error/></testsuites>',
    '<unexpected><testcase/></unexpected>',
])
def test_report_rejects_incomplete_or_failed_runs(tmp_path, xml):
    path = tmp_path / 'report.xml'
    path.write_text(xml)
    with pytest.raises(ValueError):
        report.check_report(path)


def test_report_rejects_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        report.check_report(tmp_path / 'missing.xml')


def test_report_rejects_malformed_xml(tmp_path):
    path = tmp_path / 'report.xml'
    path.write_text('<testsuites>')
    with pytest.raises(ET.ParseError):
        report.check_report(path)
