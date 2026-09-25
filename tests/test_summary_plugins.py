import importlib
import sys

import pytest

from paper_radar.cli import main
from paper_radar.core.exceptions import RadarError
from paper_radar.summarization.loader import create_summary_model, load_summary_models


def test_builtin_plugins_and_listing_do_not_require_credentials(monkeypatch, capsys):
    monkeypatch.delenv("API_KEY", raising=False)
    assert set(load_summary_models()) == {"deepseek", "compatible"}
    assert main(["summary-models"]) == 0
    assert capsys.readouterr().out.splitlines() == ["compatible", "deepseek"]


def test_unknown_provider_is_rejected_before_credentials(monkeypatch):
    monkeypatch.delenv("API_KEY", raising=False)
    with pytest.raises(RadarError, match="Unknown summary provider"):
        create_summary_model("unknown")


def test_new_module_is_discovered_created_and_closed_without_registration(tmp_path, monkeypatch):
    import paper_radar.summarization as package

    code = """
from paper_radar.summarization.base import SummaryModel
from paper_radar.core.summaries import ChineseSummary

class CustomModel(SummaryModel):
    name = "custom_test"

    @classmethod
    def create(cls, settings):
        instance = cls()
        instance.provider = cls.name
        instance.model = settings.model
        instance.base_url = "https://custom.example"
        instance.closed = False
        return instance

    def summarize(self, paper):
        return ChineseSummary("中文标题", "中文总结", ["关键要点"])

    def close(self):
        self.closed = True
"""
    (tmp_path / "custom_plugin.py").write_text(code, encoding="utf-8")
    monkeypatch.setattr(package, "__path__", [*package.__path__, str(tmp_path)])
    monkeypatch.setenv("API_KEY", "test-key")
    importlib.invalidate_caches()
    try:
        model = create_summary_model("custom_test", "my-model")
        assert model.provider == "custom_test"
        assert model.model == "my-model"
        model.close()
        assert model.closed
        (tmp_path / "duplicate_plugin.py").write_text(
            code.replace("CustomModel", "DuplicateModel"), encoding="utf-8"
        )
        importlib.invalidate_caches()
        with pytest.raises(RadarError, match="Duplicate plugin name"):
            load_summary_models()
    finally:
        sys.modules.pop("paper_radar.summarization.custom_plugin", None)
        sys.modules.pop("paper_radar.summarization.duplicate_plugin", None)
