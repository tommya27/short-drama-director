"""开场生成的契约测试：模型路径、规则回退、来源标注、manifest 白名单。

全部离线（桩客户端），不联网。
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.director_core import opening  # noqa: E402
from backend.director_core.opening import ASSET_VOCABULARY, _coerce_manifest, expand  # noqa: E402

GOOD = {
    "title": "华山一剑",
    "genre": "武侠",
    "location": "华山之巅",
    "locations": ["山门", "石阶", "崖边"],
    "world_setting": "华山论剑前夜，旧友反目。",
    "conflict": "两人为同一把剑对峙",
    "characters": [
        {"id": "a", "name": "沈青崖", "role": "protagonist", "goal": "取回师门之剑",
         "hidden_goal": "确认旧友是否背叛", "secret": "他早已把剑调包",
         "public_identity": "剑客", "true_identity": "剑客", "location": "崖边",
         "gender": "男", "appearance": "青衫长剑，眉骨有旧伤", "combat": 8,
         "personality": "克制", "possessions": "青锋剑"},
        {"id": "b", "name": "陆寒", "role": "antagonist", "goal": "带走剑",
         "hidden_goal": "掩盖当年真相", "secret": "当年是他放的火",
         "public_identity": "旧友", "true_identity": "叛徒", "location": "石阶",
         "gender": "男", "appearance": "玄衣，左手戴护腕", "combat": 9,
         "personality": "阴郁", "possessions": "断刃"},
    ],
    "items": [{"id": "sword", "name": "青锋剑", "holder": "a", "location": "崖边"}],
    "facts": [{"id": "fire", "label": "当年山门失火并非意外", "known_by": ["b"], "source": "剧中线索"}],
    "scene_manifest": {
        "scene_key": "mountain", "name": "山巅", "renderer_type": "generic3d",
        "palette": {"floor": "#8d9a86", "wall": "#b9c3b4", "wood": "#6b5a44", "accent": "#4c6b63"},
        "zones": [{"id": "山门", "position": [0, 0, 0]}, {"id": "石阶", "position": [-4, 0, 2]},
                  {"id": "崖边", "position": [4, 0, 3]}],
        "asset_set": ["outdoor", "rock", "pine", "rail", "不存在的道具"],
        "camera_presets": ["wide", "top", "focus"],
        "interaction_points": [{"id": "cliff", "label": "崖边", "position": [4, 0, 3], "item_id": "sword"}],
    },
}


class StubClient:
    def __init__(self, payload):
        self.payload = payload
        self.tags = []

    def chat_json(self, system_prompt, user_prompt, tag="", temperature=None):
        self.tags.append(tag)
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


@pytest.fixture(autouse=True)
def live_env(monkeypatch):
    monkeypatch.setenv("DIRECTOR_LLM_API_KEY", "sk-test-not-real")
    monkeypatch.delenv("DIRECTOR_OPENING_MODE", raising=False)
    yield


def test_model_path_returns_full_spec():
    result = expand("华山之巅，两位旧友为一把剑对峙", client=StubClient(GOOD))
    assert result["source"] == "llm"
    spec = result["scene_spec"]
    assert spec["title"] == "华山一剑"
    assert {a["id"] for a in spec["actors"]} == {"a", "b"}
    assert spec["locations"] == ["山门", "石阶", "崖边"]
    manifest = spec["scene_manifest"]
    assert manifest["scene_key"] == "mountain"
    assert manifest["palette"]["floor"] == "#8d9a86"
    assert manifest["zones"][1]["id"] == "石阶"
    assert "outdoor" in manifest["asset_set"]


def test_manifest_only_keeps_renderable_assets():
    manifest = _coerce_manifest(GOOD["scene_manifest"])
    assert "不存在的道具" not in manifest["asset_set"]
    assert manifest["asset_set"] == ["outdoor", "rock", "pine", "rail"]   # 按词表顺序
    assert all(name in ASSET_VOCABULARY for name in manifest["asset_set"])


def test_manifest_drops_bad_shapes():
    manifest = _coerce_manifest({
        "palette": {"floor": "#fff", "nope": "#000"},
        "zones": [{"id": "x"}, {"id": "y", "position": [1, 2]}],
        "camera_presets": ["wide", 7],
        "interaction_points": [{"id": "p", "position": [1, 0, 2]}, {"id": "q"}],
    })
    assert manifest["palette"] == {"floor": "#fff"}
    # 空字段直接省略，让前端走自己的自动布局，而不是塞空数组进去
    assert "zones" not in manifest
    assert manifest["camera_presets"] == ["wide"]
    assert manifest["interaction_points"] == [{"id": "p", "label": "p", "position": [1.0, 0.0, 2.0]}]


def test_falls_back_when_model_raises():
    result = expand("华山之巅，两位旧友对峙", client=StubClient(RuntimeError("模型返回不是 JSON")))
    assert result["source"] == "rule"
    assert "RuntimeError" in result["fallback_reason"]
    assert result["scene_spec"]["actors"], "规则路径也要给出可用角色"


def test_falls_back_when_model_shape_is_wrong():
    result = expand("游轮驾驶舱里的对峙", client=StubClient({"characters": [], "locations": []}))
    assert result["source"] == "rule"
    assert result["scene_spec"]["location"]


def test_rule_path_without_key(monkeypatch):
    monkeypatch.delenv("DIRECTOR_LLM_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = expand("客栈里的三个人")
    assert result["source"] == "rule"


def test_forced_rule_mode(monkeypatch):
    monkeypatch.setenv("DIRECTOR_OPENING_MODE", "rule")
    stub = StubClient(GOOD)
    result = expand("华山之巅", client=stub)
    assert result["source"] == "rule"
    assert stub.tags == [], "强制规则模式不应调用模型"


def test_model_source_is_reported_in_payload():
    """作者能看出这份开场是谁生成的——不做静默替换。"""
    result = expand("华山之巅", client=StubClient(GOOD))
    assert json.dumps(result, ensure_ascii=False)
    assert result.get("source") in {"llm", "rule"}
