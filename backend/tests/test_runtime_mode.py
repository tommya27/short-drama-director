"""运行模式（live / offline）与真实模型客户端的契约测试。

要点：
- 无密钥时默认离线；显式 live 但无密钥必须**拒绝启动**，不允许静默降级。
- live 模式的来源标记（事件 source=llm、草稿 source=llm_role_agents）用桩客户端验证，不联网。
"""
import json
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend import main  # noqa: E402
from backend.director_core import runtime  # noqa: E402
from backend.director_core.engine import DirectorStore  # noqa: E402
from backend.director_core.llm_client import LLMClient, LLMError, MissingKeyError, parse_json_object  # noqa: E402
from backend.director_core.offline import OfflineGenerator  # noqa: E402
from backend.director_core.sandbox import LLMCandidateGenerator  # noqa: E402

KEY_ENVS = ("DIRECTOR_LLM_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in KEY_ENVS + ("DIRECTOR_MODEL_MODE", "DIRECTOR_LLM_MODEL", "DIRECTOR_LLM_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    yield


class StubClient:
    """替代真实 HTTP 客户端：返回固定 JSON，用于验证 live 路径的来源标记。"""

    def __init__(self):
        self.tags = []

    def chat_json(self, system_prompt, user_prompt, tag="", temperature=None):
        self.tags.append(tag)
        return {"action": "把笔记本推到桌子中央", "dialogue": "先记下这一条。", "inner_thought": "",
                "action_type": "观察", "move_to": "", "referenced_event_ids": []}


def client_for(store) -> TestClient:
    main.store = store
    return TestClient(main.app)


# ---------- 模式解析 ----------

def test_defaults_to_offline_without_key():
    info = runtime.runtime_info()
    assert info["mode"] == "offline"
    assert info["generator"] == "offline_rule_v1"
    assert info["key_present"] is False
    assert info["model"] == "—"


def test_auto_live_when_key_present(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-not-real")
    info = runtime.runtime_info()
    assert info["mode"] == "live"
    assert info["generator"] == "llm_role_agents"
    assert info["key_present"] is True
    assert info["model"] and info["model"] != "—"
    assert "sk-test-not-real" not in json.dumps(info, ensure_ascii=False)


def test_explicit_mode_env_wins(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("DIRECTOR_MODEL_MODE", "offline")
    assert runtime.resolve_mode() == "offline"


def test_invalid_mode_rejected(monkeypatch):
    monkeypatch.setenv("DIRECTOR_MODEL_MODE", "turbo")
    with pytest.raises(ValueError):
        runtime.resolve_mode()


def test_live_without_key_refuses_to_start(monkeypatch, tmp_path):
    monkeypatch.setenv("DIRECTOR_MODEL_MODE", "live")
    with pytest.raises(MissingKeyError):
        runtime.build_store(tmp_path / "live.db")


def test_offline_store_builds(tmp_path):
    store, info = runtime.build_store(tmp_path / "offline.db")
    assert info["mode"] == "offline"
    assert store is not None


def test_env_file_loads_but_does_not_override(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("# 注释\nDIRECTOR_LLM_API_KEY=from-file\nDIRECTOR_MODEL_MODE=offline\n",
                       encoding="utf-8")
    monkeypatch.setenv("DIRECTOR_LLM_API_KEY", "from-env")
    runtime.load_env_file(env_file)
    assert os.environ["DIRECTOR_LLM_API_KEY"] == "from-env"   # 真实环境优先
    assert os.environ["DIRECTOR_MODEL_MODE"] == "offline"     # 文件补充


def test_missing_env_file_is_harmless(tmp_path):
    assert runtime.load_env_file(tmp_path / "not-there.env") is None


# ---------- 客户端 ----------

@pytest.mark.parametrize("text,expected", [
    ('{"a": 1}', {"a": 1}),
    ('```json\n{"a": 2}\n```', {"a": 2}),
    ('说明文字 {"a": 3} 结尾', {"a": 3}),
])
def test_parse_json_object_tolerates_wrapping(text, expected):
    assert parse_json_object(text) == expected


@pytest.mark.parametrize("text", ["", "not json at all", "[1, 2, 3]"])
def test_parse_json_object_rejects_garbage(text):
    with pytest.raises(LLMError):
        parse_json_object(text)


def test_client_requires_key():
    with pytest.raises(MissingKeyError):
        LLMClient(key="")


def test_client_describe_hides_key():
    described = LLMClient(key="sk-secret-value").describe()
    assert described["key_present"] is True
    assert "sk-secret-value" not in json.dumps(described, ensure_ascii=False)


# ---------- 来源标记（HTTP 层，不联网）----------

def test_runtime_endpoint_shape():
    body = client_for(main.store).get("/api/v1/runtime").json()
    assert body["mode"] in {"live", "offline"}
    assert body["mode"] == main.RUNTIME["mode"]
    assert set(body) >= {"mode", "generator", "model", "key_present", "label", "detail"}
    assert isinstance(body["key_present"], bool)
    # 只暴露环境变量“名字”，绝不暴露密钥内容
    assert "sk-" not in json.dumps(body)


def test_health_reports_mode():
    body = client_for(main.store).get("/health").json()
    assert body["status"] == "ok"
    assert body["model_mode"] in {"live", "offline"}


def test_offline_draft_reports_offline_source(monkeypatch):
    with TemporaryDirectory() as temp:
        store = DirectorStore(Path(temp) / "offline.db", generator_factory=lambda: OfflineGenerator())
        monkeypatch.setattr(main, "store", store)
        http = TestClient(main.app)
        scene = http.post("/api/v1/scenes", json={"title": "离线来源"}).json()
        draft = http.post(f"/api/v1/scenes/{scene['scene_id']}/drafts", json={}).json()
        assert draft["generation_source"] == OfflineGenerator.source
        events = draft["candidate_events"]
        assert events, "离线规则应产出候选事件"
        assert {event["source"] for event in events} == {OfflineGenerator.source}
        # 内部草稿记录同样带来源标记
        assert store.repo.get_draft("local", draft["draft_id"])["payload"]["source"] == OfflineGenerator.source


def test_live_draft_reports_llm_source(monkeypatch):
    stub = StubClient()
    with TemporaryDirectory() as temp:
        store = DirectorStore(Path(temp) / "live.db", generator_factory=lambda: LLMCandidateGenerator(stub))
        monkeypatch.setattr(main, "store", store)
        http = TestClient(main.app)
        scene = http.post("/api/v1/scenes", json={"title": "实时来源"}).json()
        draft = http.post(f"/api/v1/scenes/{scene['scene_id']}/drafts", json={}).json()
        assert draft["generation_source"] == "llm_role_agents"
        events = draft["candidate_events"]
        assert events, "live 模式应产出候选事件"
        assert {event["source"] for event in events} == {"llm"}
        assert all(tag.startswith("narrative_decision_") for tag in stub.tags)
        assert store.repo.get_draft("local", draft["draft_id"])["payload"]["source"] == "llm_role_agents"
        # 候选阶段不得改动正式世界
        assert http.get(f"/api/v1/scenes/{scene['scene_id']}/state").json()["revision"] == 0
