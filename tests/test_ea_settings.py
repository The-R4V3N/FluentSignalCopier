# tests/test_ea_settings.py
import json, pathlib, importlib.util
from fastapi.testclient import TestClient

APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "web_backend" / "app.py"
spec = importlib.util.spec_from_file_location("fluent_app", APP_PATH)
app_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app_module)  # now app_module.app is your FastAPI app

def test_ea_settings_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "EA_SETTINGS", tmp_path / "Fluent_ea_settings.json")
    client = TestClient(app_module.app)

    r = client.get("/api/ea-settings")
    assert r.status_code == 200
    data = r.json()
    assert "InpUseCustomLots" in data

    payload = {**data, "InpUseCustomLots": True, "InpTP1_Lots": 0.05, "InpTP2_Lots": 0.03}
    r2 = client.post("/api/ea-settings", json=payload)
    assert r2.status_code == 200
    saved = r2.json()["saved"]
    assert saved["InpUseCustomLots"] is True
    assert saved["InpTP1_Lots"] == 0.05
    assert saved["InpTP2_Lots"] == 0.03

    j = json.loads((tmp_path / "Fluent_ea_settings.json").read_text())
    assert j["InpUseCustomLots"] is True
