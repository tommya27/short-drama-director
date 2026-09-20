"""T1 美术素材：文生图（Seedream / OpenAI 兼容 images/generations）+ 本地落盘 + 来源记录。

设计约束（与项目规则一致）：
1. 只用标准库，密钥与 LLM 客户端共用（环境变量或项目 .env），**绝不外发、绝不写日志**。
2. 图片下载到 `data/assets/`，同时在 `data/assets/index.json` 记录提示词、模型、尺寸、时间戳、sha256。
   —— 这样界面上每一张图都能回答"谁生成的、用什么提示词、什么时候"。
3. 图只做视觉层（背板/立绘/道具参考），**不参与世界状态裁决**：几何与走位仍由 scene manifest 决定。
4. 失败显式抛错，不做占位假图。
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .llm_client import USER_AGENT, api_key, base_url

DEFAULT_IMAGE_MODEL = "doubao-seedream-5-0-pro-260628"
DEFAULT_SIZE = "1024x1024"
PORTRAIT_SIZE = "864x1152"
KINDS = ("backdrop", "portrait", "prop")

KIND_LABELS = {"backdrop": "场景背板", "portrait": "角色立绘", "prop": "道具参考"}

_STYLE_SUFFIX = "写实电影感，短剧剧照风格，构图干净，主体居中，无文字水印，无多余人物"


class ImageError(RuntimeError):
    """图像生成或下载失败。"""


class MissingImageKeyError(ValueError):
    """未配置图像模型密钥。"""


def image_model() -> str:
    return (os.environ.get("DIRECTOR_IMAGE_MODEL") or DEFAULT_IMAGE_MODEL).strip() or DEFAULT_IMAGE_MODEL


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def assets_dir() -> Path:
    target = Path(os.environ.get("DIRECTOR_ASSETS_DIR") or (project_root() / "data" / "assets"))
    target.mkdir(parents=True, exist_ok=True)
    return target


def index_path() -> Path:
    return assets_dir() / "index.json"


def _load_index() -> list[dict]:
    path = index_path()
    if not path.exists():
        return []
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return rows if isinstance(rows, list) else []


def _save_index(rows: list[dict]) -> None:
    index_path().write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def list_assets(scene_id: str | None = None) -> list[dict]:
    """按场景列出素材（含生成来源），最新在前。"""
    rows = _load_index()
    if scene_id:
        rows = [row for row in rows if row.get("scene_id") == scene_id]
    return sorted(rows, key=lambda row: row.get("created_at", ""), reverse=True)


def asset_file(asset_id: str) -> Path | None:
    row = next((item for item in _load_index() if item.get("asset_id") == asset_id), None)
    if not row:
        return None
    path = assets_dir() / str(row.get("file", ""))
    return path if path.exists() else None


def _record(scene_id: str, kind: str, prompt: str, model: str, size: str, raw: bytes, **extra) -> dict:
    digest = hashlib.sha256(raw).hexdigest()
    # 记录按"槽位"唯一（场景+类型+对象）：重新生成同一槽位时覆盖旧记录，不会顶掉别的场景；
    # 文件按内容去重（相同图片只存一份）。
    slot = "|".join([scene_id, kind, str(extra.get("actor_id") or ""), str(extra.get("item_id") or "")])
    asset_id = f"asset_{hashlib.sha256(slot.encode('utf-8')).hexdigest()[:16]}"
    filename = f"{digest[:16]}.png"
    if not (assets_dir() / filename).exists():
        (assets_dir() / filename).write_bytes(raw)
    row = {
        "asset_id": asset_id, "scene_id": scene_id, "kind": kind, "label": KIND_LABELS.get(kind, kind),
        "prompt": prompt, "model": model, "size": size, "file": filename,
        "sha256": digest, "bytes": len(raw), "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "url": f"/api/v1/assets/{asset_id}",
    }
    row.update({key: value for key, value in extra.items() if value is not None})
    rows = [item for item in _load_index() if item.get("asset_id") != asset_id]
    rows.append(row)
    _save_index(rows)
    return row


# ---------- 提示词（由场景设定生成，作者可覆盖）----------

def _spec_field(spec: dict, *names, default="") -> str:
    for name in names:
        value = spec.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return default


def _actors(spec: dict) -> list[dict]:
    return list(spec.get("characters") or spec.get("actors") or [])


def find_actor(spec: dict, actor_id: str) -> dict | None:
    return next((actor for actor in _actors(spec) if actor.get("id") == actor_id), None)


def backdrop_prompt(spec: dict) -> str:
    location = _spec_field(spec, "location", default="室内")
    setting = _spec_field(spec, "setting", "world_setting") or _spec_field(spec, "premise")
    world = spec.get("world") if isinstance(spec.get("world"), dict) else {}
    world_setting = world.get("setting") if isinstance(world, dict) else ""
    return (f"空无一人的{location}全景，用于短剧场景背板。环境：{setting or world_setting or '现代室内'}。"
            f"{_STYLE_SUFFIX}")


def portrait_prompt(spec: dict, actor_id: str) -> str:
    actor = find_actor(spec, actor_id)
    if actor is None:
        raise ImageError(f"场景中没有角色 {actor_id}")
    name = actor.get("name", actor_id)
    look = actor.get("appearance") or actor.get("visual_anchor") or "日常着装"
    gender = actor.get("gender") or ""
    identity = actor.get("public_identity") or actor.get("role") or ""
    return (f"短剧人物定妆照：{name}，{gender}{identity}。外形：{look}。"
            f"半身正面，中性表情，纯色背景便于抠图。{_STYLE_SUFFIX}")


def prop_prompt(spec: dict, item_id: str) -> str:
    items = spec.get("items") or {}
    item = items.get(item_id) if isinstance(items, dict) else None
    if isinstance(item, list):
        item = next((entry for entry in item if entry.get("id") == item_id), None)
    if not item:
        # 道具可能只存在于世界状态而非设定里：用 id 作为名称，仍然是真实生成
        return f"短剧道具特写：{item_id}，单独置于中性台面，产品级打光，纯色背景。{_STYLE_SUFFIX}"
    name = item.get("name", item_id)
    return f"短剧道具特写：{name}，单独置于中性台面，产品级打光，纯色背景。{_STYLE_SUFFIX}"


def build_prompt(spec: dict, kind: str, actor_id: str | None = None, item_id: str | None = None) -> str:
    if kind == "backdrop":
        return backdrop_prompt(spec)
    if kind == "portrait":
        if not actor_id:
            raise ImageError("生成角色立绘需要 actor_id")
        return portrait_prompt(spec, actor_id)
    if kind == "prop":
        if not item_id:
            raise ImageError("生成道具参考需要 item_id")
        return prop_prompt(spec, item_id)
    raise ImageError(f"不支持的素材类型：{kind}（可用：{'/'.join(KINDS)}）")


# ---------- 客户端 ----------

class ImageClient:
    """OpenAI 兼容的图像生成客户端（默认 doubao-seedream 系列）。"""

    def __init__(self, key: str | None = None, base: str | None = None, model: str | None = None,
                 timeout: float | None = None, opener=None):
        self._key = key if key is not None else api_key()
        self.base = (base or base_url()).rstrip("/")
        self.model = model or image_model()
        self.timeout = timeout if timeout is not None else float(os.environ.get("DIRECTOR_IMAGE_TIMEOUT", "120"))
        self._opener = opener or urllib.request.urlopen
        if not self._key:
            raise MissingImageKeyError("图像生成需要模型密钥：请在 .env 或环境变量里设置 DIRECTOR_LLM_API_KEY")

    def describe(self) -> dict:
        return {"model": self.model, "base_url": self.base, "key_present": bool(self._key)}

    def _post(self, body: dict) -> dict:
        request = urllib.request.Request(
            f"{self.base}/images/generations",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self._key}",
                     "User-Agent": os.environ.get("DIRECTOR_LLM_USER_AGENT", USER_AGENT),
                     "Accept": "application/json"},
            method="POST",
        )
        try:
            with self._opener(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise ImageError(f"图像接口返回 HTTP {exc.code}：{detail}") from exc
        except urllib.error.URLError as exc:
            raise ImageError(f"无法连接图像接口：{exc.reason}") from exc

    def generate(self, prompt: str, size: str = DEFAULT_SIZE) -> dict:
        """返回 {"url"|"b64", "model", "prompt", "size"}；供应商拒绝尺寸时退回默认尺寸。"""
        def post(chosen: str) -> dict:
            return self._post({"model": self.model, "prompt": prompt, "size": chosen, "n": 1})

        try:
            data = post(size)
        except ImageError as exc:
            if "size" in str(exc) and size != DEFAULT_SIZE:
                size = DEFAULT_SIZE          # 尺寸不被支持时退回默认，仍是真实生成
                data = post(size)
            else:
                raise
        if isinstance(data.get("error"), dict) or isinstance(data.get("detail"), (str, dict)):
            raise ImageError(f"图像接口报错：{str(data.get('error') or data.get('detail'))[:300]}")
        item = (data.get("data") or [{}])[0]
        if item.get("url"):
            return {"url": item["url"], "model": data.get("model", self.model), "prompt": prompt, "size": size}
        if item.get("b64_json"):
            return {"b64": item["b64_json"], "model": data.get("model", self.model), "prompt": prompt, "size": size}
        raise ImageError(f"图像接口未返回图片：{str(data)[:200]}")

    def fetch(self, url: str) -> bytes:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with self._opener(request, timeout=self.timeout) as response:
                return response.read()
        except (urllib.error.HTTPError, urllib.error.URLError) as exc:
            raise ImageError(f"下载生成图片失败：{exc}") from exc


def generate_artifact(scene_id: str, spec: dict, kind: str, *, actor_id: str | None = None,
                      item_id: str | None = None, prompt: str | None = None, size: str | None = None,
                      client: ImageClient | None = None) -> dict:
    """生成一张素材并落盘；返回带来源信息的记录。"""
    if kind not in KINDS:
        raise ImageError(f"不支持的素材类型：{kind}")
    final_prompt = (prompt or "").strip() or build_prompt(spec, kind, actor_id, item_id)
    final_size = size or (PORTRAIT_SIZE if kind == "portrait" else DEFAULT_SIZE)
    client = client or ImageClient()
    result = client.generate(final_prompt, final_size)
    actual_size = result.get("size", final_size)   # 供应商可能退回默认尺寸，按实际记录
    raw = base64.b64decode(result["b64"]) if result.get("b64") else client.fetch(result["url"])
    if not raw:
        raise ImageError("生成的图片内容为空")
    return _record(scene_id, kind, final_prompt, result.get("model", client.model), actual_size, raw,
                   actor_id=actor_id, item_id=item_id,
                   source_url=(result.get("url") or "")[:300] or None)


def runtime_info() -> dict:
    """图像能力信息（供界面显示），不含密钥。"""
    key = api_key()
    return {"image_model": image_model(), "key_present": bool(key), "configured": bool(key),
            "kinds": [{"kind": kind, "label": KIND_LABELS[kind]} for kind in KINDS],
            "assets_dir": str(assets_dir()), "style_suffix": _STYLE_SUFFIX}
