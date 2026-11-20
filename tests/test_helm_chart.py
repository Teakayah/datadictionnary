from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import jsonschema
import pytest
import yaml

CHART_DIR = Path(__file__).resolve().parents[1] / "charts" / "data-dictionary"


def _deep_merge(base: dict, override: dict) -> dict:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _load_schema() -> dict:
    return json.loads((CHART_DIR / "values.schema.json").read_text(encoding="utf-8"))


def test_chart_metadata():
    chart = _load_yaml(CHART_DIR / "Chart.yaml")
    assert chart["apiVersion"] == "v2"
    assert chart["name"] == "data-dictionary"
    assert chart["type"] == "application"
    assert chart["version"]


@pytest.mark.parametrize(
    "preset",
    ["values.yaml", "values-showcase.yaml", "values-prod.yaml"],
)
def test_values_profiles_validate_against_schema(preset: str):
    schema = _load_schema()
    base = _load_yaml(CHART_DIR / "values.yaml")
    values = base if preset == "values.yaml" else _deep_merge(base, _load_yaml(CHART_DIR / preset))
    jsonschema.validate(instance=values, schema=schema)


def test_schema_rejects_mock_auth_in_production():
    schema = _load_schema()
    values = _load_yaml(CHART_DIR / "values.yaml")
    values["config"]["environment"] = "production"
    values["config"]["features"]["enableMockAuth"] = True

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=values, schema=schema)


def test_prod_preset_disables_chart_managed_secrets():
    base = _load_yaml(CHART_DIR / "values.yaml")
    prod = _deep_merge(base, _load_yaml(CHART_DIR / "values-prod.yaml"))
    assert prod["secrets"]["create"] is False
    assert prod["secrets"]["existingSecret"]
    assert prod["config"]["features"]["enableMockAuth"] is False
    assert prod["config"]["features"]["demoData"] is False


def test_showcase_preset_is_offline_self_contained():
    base = _load_yaml(CHART_DIR / "values.yaml")
    showcase = _deep_merge(base, _load_yaml(CHART_DIR / "values-showcase.yaml"))
    assert showcase["config"]["environment"] == "development"
    assert showcase["config"]["features"]["enableMockAuth"] is True
    assert showcase["config"]["features"]["demoData"] is True
    assert showcase["storage"]["enabled"] is False
    assert showcase["syncWorker"]["enabled"] is False
    assert showcase["cronJob"]["enabled"] is False


def test_cronjob_template_runs_sync_metadata():
    cronjob_tpl = (CHART_DIR / "templates" / "cronjob.yaml").read_text(encoding="utf-8")
    assert "scripts/sync_metadata.py" in cronjob_tpl
    assert "nightly_sync.py" not in cronjob_tpl


def test_templates_have_balanced_helm_delimiters():
    tpl_dir = CHART_DIR / "templates"
    files = sorted(p for p in tpl_dir.iterdir() if p.is_file())
    assert files, "Expected Helm templates in charts/data-dictionary/templates/"

    block_open_re = re.compile(r"\{\{-?\s*(?:if|range|with|define)\b")
    block_end_re = re.compile(r"\{\{-?\s*end\b")

    for path in files:
        text = path.read_text(encoding="utf-8")
        # Strip Go template comments before checking block balance
        no_comments = re.sub(r"\{\{-?\s*/\*.*?\*/\s*-?\}\}", "", text, flags=re.DOTALL)
        assert no_comments.count("{{") == no_comments.count("}}"), f"Unbalanced braces in {path.name}"
        opens = len(block_open_re.findall(no_comments))
        ends = len(block_end_re.findall(no_comments))
        assert opens == ends, f"Unbalanced template blocks in {path.name}: {opens} opens vs {ends} ends"
