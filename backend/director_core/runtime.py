"""运行模式：live（真实模型）或 offline（离线规则）。

规则：
- 显式指定 > 环境变量 DIRECTOR_MODEL_MODE > 自动判断（有密钥=live，无密钥=offline）。
- 显式 live 但没有密钥 -> 直接报错。**绝不静默降级**，否则"离线规则"会被当成"模型生成"。
- 模式与模型信息会通过 /api/v1/runtime 暴露给前端做徽标，密钥永不外发。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .engine import DirectorStore
from .llm_client import DEFAULT_BASE_URL, DEFAULT_MODEL, LLMClient, MissingKeyError, KEY_ENV_NAMES, api_key, base_url, model_name
from .offline import OfflineGenerator
from .sandbox import LLMCandidateGenerator

MODES = ("live", "offline")
MODE_ENV = "DIRECTOR_MODEL_MODE"
LIVE_GENERATOR = "llm_role_agents"


def project_root() -> Path:
    """backend/director_core/runtime.py -> 项目根目录。"""
    return Path(__file__).resolve().parents[2]


def load_env_file(path: str | Path | None = None) -> Path | None:
    """极简 .env 读取：KEY=VALUE，支持 # 注释与引号；已存在的环境变量优先，不覆盖。"""
    target = Path(path) if path else project_root() / ".env"
    if not target.exists():
        return None
    for raw in target.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export "):].strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
    return target


def resolve_mode(explicit: str | None = None) -> str:
    """返回 'live' 或 'offline'。"""
    raw = (explicit if explicit is not None else os.environ.get(MODE_ENV, "")).strip().lower()
    if raw:
        if raw not in MODES:
            raise ValueError(f"{MODE_ENV} 只支持 {' / '.join(MODES)}，收到 {raw!r}")
        return raw
    return "live" if api_key() else "offline"


def runtime_info(mode: str | None = None) -> dict[str, Any]:
    """可安全外发的运行信息（含前端徽标文案），不含任何密钥。"""
    resolved = resolve_mode(mode)
    key_present = bool(api_key())
    model = model_name() if resolved == "live" else "—"
    return {
        "mode": resolved,
        "generator": LIVE_GENERATOR if resolved == "live" else OfflineGenerator.source,
        "model": model,
        "base_url": base_url() if resolved == "live" else "—",
        "key_present": key_present,
        "label": f"真模型试演 · {model}" if resolved == "live" else "离线规则试演",
        "key_env_names": list(KEY_ENV_NAMES),
        "mode_env": MODE_ENV,
        "detail": (
            "角色候选由真实模型生成（事件 source=llm，草稿 source=llm_role_agents）"
            if resolved == "live" else
            "角色候选由本地确定性规则生成，不调用模型（事件 source=offline_rule_v1）"
        ),
    }


def build_generator():
    """按当前模式返回一个候选生成器实例。"""
    if resolve_mode() == "live":
        return LLMCandidateGenerator(LLMClient())
    return OfflineGenerator()


def build_store(db_path=None, mode: str | None = None) -> tuple[DirectorStore, dict[str, Any]]:
    """构建带模式的 DirectorStore，并返回 (store, 运行信息)。"""
    info = runtime_info(mode)
    if info["mode"] == "live" and not info["key_present"]:
        raise MissingKeyError(
            "live 模式需要模型密钥：请在项目 .env 或环境变量里设置 "
            + " 或 ".join(KEY_ENV_NAMES) + "；拒绝静默降级为离线规则。"
        )
    factory = (lambda: LLMCandidateGenerator(LLMClient())) if info["mode"] == "live" else (lambda: OfflineGenerator())
    return DirectorStore(db_path, generator_factory=factory), info


__all__ = ["MODES", "MODE_ENV", "LIVE_GENERATOR", "build_generator", "build_store", "load_env_file",
           "project_root", "resolve_mode", "runtime_info", "DEFAULT_BASE_URL", "DEFAULT_MODEL"]
