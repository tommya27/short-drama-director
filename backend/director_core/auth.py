"""账号与令牌（移植自用户旧小说平台的 `api/auth.py`，改写环境变量名与目录；不引入任何新依赖）。

来源与复用：`D:/Deepseek harness workplace/小说写作平台/api/auth.py`
（移植范围与源文件 sha256 记录在 `docs/PROVENANCE.md`）。改写的部分：
- 环境变量前缀 NOOVEL_* → DIRECTOR_*；
- 账号目录默认 `data/auth`（新项目自己的数据目录），不读写旧平台的 `output/auth`；
- 令牌默认有效期 30 天 → **7 天**（本版要公网访问，缩短暴露窗口）；
- 口令最短 6 位 → **8 位**（同上）；
- 保持等价：PBKDF2-HMAC-SHA256 / 20 万次迭代 / 自签 HMAC 令牌 / token_version 全量吊销 / 原子写账号表。

设计要点（移植时的原有取舍，保留）：
* 令牌是**自签 HMAC**（不是 JWT 库）：`base64url(payload).base64url(hmac_sha256(secret, payload))`，
  payload 含用户名、过期时间与令牌版本；校验用 `hmac.compare_digest` 防时序侧信道。
* 自签令牌是无状态的，改口令/停用账号**不会**自动让旧令牌失效 → 用 `token_version` 做到「一键全撤」。
* 账号表先写临时文件再替换，避免半截文件。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
#: 账号/密钥目录；可用 DIRECTOR_AUTH_DIR 覆盖（测试与多实例部署用）
AUTH_DIR = Path(os.environ.get("DIRECTOR_AUTH_DIR") or (PROJECT_ROOT / "data" / "auth"))
USERS_FILE = AUTH_DIR / "users.json"
SECRET_FILE = AUTH_DIR / "secret.key"

PBKDF2_ITERATIONS = 200_000
#: 令牌有效期（天）。公网部署建议 7 天以内
TOKEN_TTL_DAYS = int(os.environ.get("DIRECTOR_TOKEN_TTL_DAYS", "7"))
#: 每用户每日任务配额（0 = 不限）
QUOTA_DAILY_TASKS = int(os.environ.get("DIRECTOR_QUOTA_DAILY_TASKS", "0"))
#: 每用户同时进行中的任务数上限（0 = 不限）
QUOTA_MAX_CONCURRENT = int(os.environ.get("DIRECTOR_QUOTA_MAX_CONCURRENT", "1"))

USERNAME_RE = re.compile(r"^[A-Za-z0-9_-]{2,32}$")
MIN_PASSWORD_LEN = int(os.environ.get("DIRECTOR_MIN_PASSWORD_LEN", "8"))


class AuthError(Exception):
    """账号/令牌相关的业务错误（路由层转成 4xx）。"""


# ── 基础工具 ───────────────────────────────────────────────────────────────

def auth_dir() -> Path:
    AUTH_DIR.mkdir(parents=True, exist_ok=True)
    return AUTH_DIR


def auth_secret() -> bytes:
    """令牌签名密钥：优先环境变量，否则落盘 `secret.key`（首次自动生成）。"""
    env = os.environ.get("DIRECTOR_AUTH_SECRET")
    if env:
        return hashlib.sha256(env.encode("utf-8")).digest()
    auth_dir()
    if not SECRET_FILE.exists():
        SECRET_FILE.write_text(secrets.token_urlsafe(48), encoding="utf-8")
    return hashlib.sha256(SECRET_FILE.read_text(encoding="utf-8").strip().encode("utf-8")).digest()


def username_slug(username: str) -> str:
    """用户名 → 存储键（小写；账号体系已限制字符集，可直接落盘）。"""
    return (username or "").strip().lower()


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def _hash_password(password: str, salt_hex: str, iterations: int = PBKDF2_ITERATIONS) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), iterations).hex()


# ── 账号表读写 ─────────────────────────────────────────────────────────────

def _empty_store() -> Dict[str, dict]:
    return {"version": 1, "users": {}}


def load_users() -> Dict[str, dict]:
    """读账号表；文件缺失/损坏时返回空表（不抛异常）。"""
    try:
        if not USERS_FILE.exists():
            return _empty_store()
        data = json.loads(USERS_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "users" not in data:
            return _empty_store()
        return data
    except Exception:  # noqa: BLE001
        return _empty_store()


def save_users(store: Dict[str, dict]) -> None:
    """原子写账号表（先写临时文件再替换，避免半截文件）。"""
    auth_dir()
    tmp = USERS_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(USERS_FILE)


def get_user(username: str) -> Optional[dict]:
    return load_users()["users"].get(username_slug(username))


def list_users() -> List[dict]:
    """列出账号（不含盐与口令散列）。"""
    out = []
    for slug, rec in load_users()["users"].items():
        out.append({
            "username": rec.get("username", slug), "slug": slug,
            "is_admin": bool(rec.get("is_admin")), "disabled": bool(rec.get("disabled")),
            "created_at": rec.get("created_at"), "last_login_at": rec.get("last_login_at"),
            "daily_tasks": rec.get("daily_tasks"), "token_version": int(rec.get("token_version", 1)),
        })
    out.sort(key=lambda r: str(r.get("created_at") or ""))
    return out


def has_users() -> bool:
    """是否已经建过账号。没有账号时服务保持"单机单用户"旧行为（不强制登录）。"""
    return bool(load_users()["users"])


def create_user(username: str, password: str, *, is_admin: bool = False,
                daily_tasks: Optional[int] = None) -> dict:
    """新建账号（用户名已存在 / 格式不合法 / 口令过短 → AuthError）。"""
    name = (username or "").strip()
    if not USERNAME_RE.match(name):
        raise AuthError("用户名只能是 2–32 位的字母、数字、下划线或短横线")
    if len(password or "") < MIN_PASSWORD_LEN:
        raise AuthError(f"口令至少 {MIN_PASSWORD_LEN} 位")
    store = load_users()
    slug = username_slug(name)
    if slug in store["users"]:
        raise AuthError(f"账号已存在：{slug}")
    salt = secrets.token_hex(16)
    store["users"][slug] = {
        "username": name,
        "salt": salt,
        "hash": _hash_password(password, salt),
        "iterations": PBKDF2_ITERATIONS,
        "token_version": 1,          # 递增即让该账号所有已签发令牌失效（见 verify_token）
        "is_admin": bool(is_admin),
        "disabled": False,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "last_login_at": None,
        "daily_tasks": daily_tasks,
    }
    save_users(store)
    return {"username": name, "is_admin": bool(is_admin)}


def set_disabled(username: str, disabled: bool = True) -> None:
    store = load_users()
    slug = username_slug(username)
    if slug not in store["users"]:
        raise AuthError(f"账号不存在：{slug}")
    store["users"][slug]["disabled"] = bool(disabled)
    if disabled:
        store["users"][slug]["token_version"] = int(store["users"][slug].get("token_version", 1)) + 1
    save_users(store)


def set_password(username: str, password: str) -> None:
    if len(password or "") < MIN_PASSWORD_LEN:
        raise AuthError(f"口令至少 {MIN_PASSWORD_LEN} 位")
    store = load_users()
    slug = username_slug(username)
    if slug not in store["users"]:
        raise AuthError(f"账号不存在：{slug}")
    salt = secrets.token_hex(16)
    store["users"][slug]["salt"] = salt
    store["users"][slug]["hash"] = _hash_password(password, salt)
    store["users"][slug]["iterations"] = PBKDF2_ITERATIONS
    # 改口令 = 旧会话一并作废，避免"改了口令但别人手里的令牌还能用"
    store["users"][slug]["token_version"] = int(store["users"][slug].get("token_version", 1)) + 1
    save_users(store)


def delete_user(username: str) -> None:
    store = load_users()
    slug = username_slug(username)
    if slug not in store["users"]:
        raise AuthError(f"账号不存在：{slug}")
    store["users"].pop(slug)
    save_users(store)


def revoke_tokens(username: str) -> int:
    """吊销该账号全部已签发令牌（令牌版本 +1），返回新版本号。"""
    store = load_users()
    slug = username_slug(username)
    if slug not in store["users"]:
        raise AuthError(f"账号不存在：{slug}")
    version = int(store["users"][slug].get("token_version", 1)) + 1
    store["users"][slug]["token_version"] = version
    save_users(store)
    return version


# ── 登录与令牌 ─────────────────────────────────────────────────────────────

def verify_password(username: str, password: str) -> bool:
    rec = get_user(username)
    if not rec or rec.get("disabled"):
        return False
    salt = rec.get("salt") or ""
    iterations = int(rec.get("iterations") or PBKDF2_ITERATIONS)
    try:
        candidate = _hash_password(password or "", salt, iterations)
    except ValueError:
        return False
    return hmac.compare_digest(candidate, str(rec.get("hash") or ""))


def login(username: str, password: str) -> Tuple[str, int, dict]:
    """校验口令并签发令牌，返回 (token, 过期秒, 账号信息)。"""
    if not verify_password(username, password):
        raise AuthError("账号或口令不正确")
    store = load_users()
    slug = username_slug(username)
    store["users"][slug]["last_login_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    save_users(store)
    token, exp = issue_token(slug)
    rec = store["users"][slug]
    return token, exp, {"username": rec.get("username", slug), "is_admin": bool(rec.get("is_admin"))}


def issue_token(username: str, ttl_days: Optional[int] = None) -> Tuple[str, int]:
    """签发令牌，返回 (token, 过期时间戳秒)。"""
    ttl = TOKEN_TTL_DAYS if ttl_days is None else int(ttl_days)
    exp = int(time.time()) + ttl * 86400
    rec = get_user(username) or {}
    payload = json.dumps({"u": username_slug(username), "exp": exp,
                          "v": int(rec.get("token_version", 1))},
                         separators=(",", ":")).encode("utf-8")
    body = _b64e(payload)
    sig = _b64e(hmac.new(auth_secret(), body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{sig}", exp


def verify_token(token: str) -> Optional[str]:
    """校验令牌，返回用户名；无效/过期/被停用/已吊销 → None。"""
    try:
        body, sig = (token or "").split(".", 1)
    except ValueError:
        return None
    expected = _b64e(hmac.new(auth_secret(), body.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(expected, sig):
        return None
    try:
        payload = json.loads(_b64d(body))
    except Exception:  # noqa: BLE001
        return None
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    rec = get_user(str(payload.get("u", "")))
    if not rec or rec.get("disabled"):
        return None
    if int(payload.get("v", 1)) != int(rec.get("token_version", 1)):
        return None
    return rec.get("username") or str(payload.get("u"))


def bearer_token(header_value: Optional[str]) -> Optional[str]:
    """从 `Authorization: Bearer <token>` 里取令牌。"""
    if not header_value:
        return None
    parts = header_value.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def is_admin(username: Optional[str]) -> bool:
    rec = get_user(username or "")
    return bool(rec and rec.get("is_admin"))


def daily_quota_for(username: str) -> int:
    rec = get_user(username) or {}
    val = rec.get("daily_tasks")
    return QUOTA_DAILY_TASKS if val is None else int(val)


def owner_username() -> Optional[str]:
    """回环请求的默认身份：最早创建的管理员，其次最早的账号；没有任何账号 → None。

    None 的语义是「还没建账号」——此时保持单机旧行为（owner='local'），
    因此在开始分享给别人之前，现有演示方式完全不变。
    """
    users = list(load_users()["users"].values())
    if not users:
        return None
    admins = [r for r in users if r.get("is_admin")]
    pool = admins or users
    pool.sort(key=lambda r: str(r.get("created_at") or ""))
    return pool[0].get("username")
