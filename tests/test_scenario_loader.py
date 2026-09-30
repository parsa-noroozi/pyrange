from pathlib import Path

import pytest
from pydantic import ValidationError

from pyrange.core import load_scenario


def test_loads_valid_scenario(tmp_path: Path) -> None:
    scenario_file = tmp_path / "scenario.yaml"
    scenario_file.write_text(
        """
name: test-lab

network:
  name: test-net
  subnet: 172.28.10.0/24

machines:
  - name: web
    image: nginx:alpine
    ip: 172.28.10.10
""".strip(),
        encoding="utf-8",
    )

    scenario = load_scenario(scenario_file)

    assert scenario.name == "test-lab"
    assert scenario.network.name == "test-net"
    assert len(scenario.machines) == 1


def test_rejects_non_mapping_yaml(tmp_path: Path) -> None:
    scenario_file = tmp_path / "scenario.yaml"
    scenario_file.write_text(
        "- one\n- two\n- three\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="scenario file must contain a YAML mapping",
    ):
        load_scenario(scenario_file)


def test_rejects_invalid_scenario(tmp_path: Path) -> None:
    scenario_file = tmp_path / "scenario.yaml"
    scenario_file.write_text(
        """
name: invalid-lab

network:
  name: test-net
  subnet: 172.28.10.0/24

machines:
  - name: web
    image: nginx:alpine
    ip: 10.0.0.5
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="is outside subnet"):
        load_scenario(scenario_file)


def test_missing_file_raises_file_not_found() -> None:
    with pytest.raises(FileNotFoundError):
        load_scenario("does-not-exist.yaml")
