"""T1 美术素材的契约测试：提示词、落盘来源记录、错误传播、密钥不外发。

全部使用桩客户端，不发起真实网络请求；素材目录通过 DIRECTOR_ASSETS_DIR 指向临时目录。
"""
import base64
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend import main  # noqa: E402
from backend.director_core import images as image_assets  # noqa: E402
from backend.director_core.images import (  # noqa: E402
    ImageClient, ImageError, MissingImageKeyError, backdrop_prompt, build_prompt,
    generate_artifact, list_assets, portrait_prompt, prop_prompt, runtime_info,
)

# 1x1 透明 PNG，够用于落盘与静态服务的字节校验
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg==")

SPEC = {
    "title": "董事会", "location": "会议室",
    "characters": [
        {"id": "ceo", "name": "顾承宇", "role": "董事长", "gender": "男",
         "public_identity": "公司创始人", "appearance": "深色西装，短发，眼神锐利"},
        {"id": "cfo", "name": "陈曦", "role": "财务总监", "gender": "女",
         "public_identity": "财务总监", "visual_anchor": "细框眼镜+素色衬衫"},
    ],
    "items": {"item_contract": {"id": "item_contract", "name": "供应商合同"}},
    "world": {"setting": "现代都市，董事会正在审议一份合同"},
}


class StubImageClient:
    """返回 base64 图片的桩客户端。"""

    def __init__(self):
        self.model = "stub-image-model"
        self.prompts = []

    def generate(self, prompt, size=image_assets.DEFAULT_SIZE):
        self.prompts.append({"prompt": prompt, "size": size})
        return {"b64": base64.b64encode(PNG_1X1).decode("ascii"), "model": self.model, "prompt": prompt}

    def fetch(self, url):  # pragma: no cover - 桩返回 base64，不走这里
        return PNG_1X1


@pytest.fixture(autouse=True)
def temp_assets(monkeypatch, tmp_path):
    monkeypatch.setenv("DIRECTOR_ASSETS_DIR", str(tmp_path / "assets"))
    monkeypatch.delenv("DIRECTOR_LLM_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    yield


# ---------- 提示词 ----------

def test_backdrop_prompt_uses_scene_fields():
    prompt = backdrop_prompt(SPEC)
    assert "会议室" in prompt and "空无一人" in prompt
    assert "董事会正在审议" in prompt or "现代都市" in prompt


def test_portrait_prompt_prefers_appearance_then_anchor():
    assert "深色西装" in portrait_prompt(SPEC, "ceo")
    assert "细框眼镜" in portrait_prompt(SPEC, "cfo")
    assert "顾承宇" in portrait_prompt(SPEC, "ceo")


def test_prop_prompt_falls_back_to_id():
    assert "供应商合同" in prop_prompt(SPEC, "item_contract")
    assert "item_unknown" in prop_prompt(SPEC, "item_unknown")


def test_build_prompt_rejects_bad_input():
    with pytest.raises(ImageError):
        build_prompt(SPEC, "poster")
    with pytest.raises(ImageError):
        build_prompt(SPEC, "portrait")           # 缺 actor_id
    with pytest.raises(ImageError):
        build_prompt(SPEC, "prop")               # 缺 item_id


# ---------- 生成与来源记录 ----------

def test_generate_artifact_records_provenance():
    stub = StubImageClient()
    row = generate_artifact("scene_x", SPEC, "backdrop", client=stub)
    assert row["kind"] == "backdrop" and row["scene_id"] == "scene_x"
    assert row["model"] == "stub-image-model"
    assert row["sha256"] and row["bytes"] == len(PNG_1X1)
    assert row["created_at"] and row["url"] == f"/api/v1/assets/{row['asset_id']}"
    assert row["prompt"] == stub.prompts[0]["prompt"]
    saved = Path(image_assets.assets_dir()) / row["file"]
    assert saved.exists() and saved.read_bytes() == PNG_1X1
    assert image_assets.asset_file(row["asset_id"]) == saved


def test_portrait_uses_portrait_size_and_actor_id():
    stub = StubImageClient()
    row = generate_artifact("scene_x", SPEC, "portrait", actor_id="ceo", client=stub)
    assert row["actor_id"] == "ceo"
    assert stub.prompts[0]["size"] == image_assets.PORTRAIT_SIZE
    assert "顾承宇" in row["prompt"]


def test_author_prompt_overrides_builder():
    stub = StubImageClient()
    row = generate_artifact("scene_x", SPEC, "backdrop", prompt="作者自己写的提示词", client=stub)
    assert row["prompt"] == "作者自己写的提示词"


def test_list_assets_filters_by_scene():
    stub = StubImageClient()
    generate_artifact("scene_a", SPEC, "backdrop", client=stub)
    generate_artifact("scene_b", SPEC, "backdrop", client=stub)
    assert {row["scene_id"] for row in list_assets("scene_a")} == {"scene_a"}
    assert len(list_assets()) >= 2


def test_generate_artifact_propagates_error_without_partial_record():
    class Broken(StubImageClient):
        def generate(self, prompt, size=image_assets.DEFAULT_SIZE):
            raise ImageError("上游 502")

    before = len(list_assets())
    with pytest.raises(ImageError):
        generate_artifact("scene_x", SPEC, "backdrop", client=Broken())
    assert len(list_assets()) == before


def test_image_client_requires_key():
    with pytest.raises(MissingImageKeyError):
        ImageClient(key="")


def test_runtime_info_never_leaks_key(monkeypatch):
    monkeypatch.setenv("DIRECTOR_LLM_API_KEY", "sk-secret-image-key")
    info = runtime_info()
    assert info["key_present"] is True and info["configured"] is True
    assert "sk-secret-image-key" not in json.dumps(info, ensure_ascii=False)
    assert info["image_model"]


# ---------- HTTP 层 ----------

def test_artifact_endpoints(monkeypatch):
    from tempfile import TemporaryDirectory
    from backend.director_core.engine import DirectorStore

    monkeypatch.setattr(image_assets, "ImageClient", lambda *a, **k: StubImageClient())
    with TemporaryDirectory() as temp:
        monkeypatch.setattr(main, "store", DirectorStore(Path(temp) / "art.db"))
        http = TestClient(main.app)
        scene = http.post("/api/v1/scenes", json={"title": "素材接口"}).json()
        sid = scene["scene_id"]

        assert http.get("/api/v1/images/runtime").status_code == 200
        assert http.get(f"/api/v1/scenes/{sid}/artifacts").json() == []

        created = http.post(f"/api/v1/scenes/{sid}/artifacts", json={"kind": "backdrop"})
        assert created.status_code == 201, created.text
        asset = created.json()
        assert asset["kind"] == "backdrop" and asset["model"] == "stub-image-model"

        assert len(http.get(f"/api/v1/scenes/{sid}/artifacts").json()) == 1
        image = http.get(asset["url"])
        assert image.status_code == 200 and image.content == PNG_1X1
        assert image.headers["content-type"].startswith("image/png")

        assert http.get("/api/v1/assets/asset_missing").status_code == 404
        assert http.post(f"/api/v1/scenes/{sid}/artifacts", json={"kind": "poster"}).status_code == 422
        assert http.post(f"/api/v1/scenes/{sid}/artifacts", json={"kind": "portrait"}).status_code == 502
