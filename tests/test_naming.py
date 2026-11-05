import pytest

from pyrange.engine.naming import build_resource_name


@pytest.mark.parametrize(
    "kind",
    ["container", "network", "snapshot"],
)
def test_distinguishes_component_boundaries(kind: str) -> None:
    first = build_resource_name(kind, "alpha-beta", "web")
    second = build_resource_name(kind, "alpha", "beta-web")

    assert first != second


def test_name_matches_fixed_vector() -> None:
    expected = (
        "pyrange-v2-container-"
        "559f31ac0beae6673a9c15ba9800d7ae"
        "623562c205d659266daec0d23a110df1"
    )

    assert build_resource_name(
        "container", "alpha-beta", "web"
    ) == expected


def test_resource_kinds_are_separate() -> None:
    names = {
        build_resource_name(kind, "lab", "web")
        for kind in ("container", "network", "snapshot")
    }

    assert len(names) == 3


def test_rejects_unknown_kind() -> None:
    with pytest.raises(ValueError, match="unsupported resource kind"):
        build_resource_name("unknown", "lab", "web")


@pytest.mark.parametrize(
    "scenario_name, resource_name",
    [("", "web"), ("lab", "")],
)
def test_rejects_empty_names(
    scenario_name: str,
    resource_name: str,
) -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        build_resource_name("container", scenario_name, resource_name)


@pytest.mark.parametrize("invalid_name", [None, 123])
def test_rejects_non_string_names(invalid_name: object) -> None:
    with pytest.raises(TypeError, match="must be strings"):
        build_resource_name("container", invalid_name, "web")

    with pytest.raises(TypeError, match="must be strings"):
        build_resource_name("container", "lab", invalid_name)
