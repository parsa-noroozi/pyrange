from pathlib import Path

import yaml

from pyrange.models import ScenarioConfig


def load_scenario(path: str | Path) -> ScenarioConfig:
    scenario_path = Path(path)

    with scenario_path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)

    if not isinstance(data, dict):
        raise ValueError("scenario file must contain a YAML mapping")

    return ScenarioConfig.model_validate(data)
