"""Reject empty, failed, or skipped pytest JUnit reports at a CI gate."""
import argparse
from pathlib import Path
import xml.etree.ElementTree as ET


def check_report(path: Path) -> int:
    root = ET.parse(path).getroot()
    if root.tag not in {'testsuites', 'testsuite'}:
        raise ValueError(f'Unexpected JUnit root: {root.tag}')
    cases = list(root.iter('testcase'))
    if not cases:
        raise ValueError('No test cases were recorded')
    # Include suite-level errors as well as ordinary test failures.
    bad = [element.tag for element in root.iter()
           if element.tag in {'skipped', 'failure', 'error'}]
    if bad:
        raise ValueError(f'JUnit gate rejected report: {bad}')
    print(f'JUnit gate passed: {len(cases)} tests, no skips or failures')
    return len(cases)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    args = parser.parse_args()
    try:
        check_report(args.report)
    except (OSError, ValueError, ET.ParseError) as exc:
        parser.exit(1, f'{exc}\n')
