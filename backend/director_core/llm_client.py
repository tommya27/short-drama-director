"""真实模型客户端（live 模式专用）。

设计约束：
1. 只用标准库，不引入新依赖。
2. 密钥只从环境变量或项目 .env 读取，**绝不打印、绝不写日志、绝不返回给前端**。
3. 失败必须显式抛错，不静默降级——静默降级会让"离线规则"被当成"真模型生成"。
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"
#: 网关/WAF 会按 UA 拦截（实测 Cloudflare 1010），因此显式声明客户端标识
USER_AGENT = "short-drama-director/0.1 (+local openai-compatible client)"
#: 密钥来源优先级（先匹配者生效）
KEY_ENV_NAMES = ("DIRECTOR_LLM_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY")

_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


class LLMError(RuntimeError):
    """模型调用失败（网络、HTTP 状态码或返回内容不是 JSON）。"""


class MissingKeyError(ValueError):
    """live 模式缺少模型密钥。"""


def api_key() -> str:
    """返回可用的模型密钥，没有则返回空串。调用方不得记录返回值。"""
    for name in KEY_ENV_NAMES:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return ""


def has_key() -> bool:
    return bool(api_key())


def base_url() -> str:
    return (os.environ.get("DIRECTOR_LLM_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")


def model_name() -> str:
    return (os.environ.get("DIRECTOR_LLM_MODEL") or DEFAULT_MODEL).strip() or DEFAULT_MODEL


def _timeout() -> float:
    try:
        return max(5.0, float(os.environ.get("DIRECTOR_LLM_TIMEOUT", "60")))
    except ValueError:
        return 60.0


def parse_json_object(text: str) -> dict:
    """从模型输出里取出 JSON 对象，容忍 ```json 围栏与前后缀说明。"""
    if not isinstance(text, str) or not text.strip():
        raise LLMError("模型返回了空内容")
    cleaned = _FENCE.sub("", text.strip())
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise LLMError(f"模型返回不是 JSON 对象：{cleaned[:120]}")
        try:
            payload = json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError as exc:
            raise LLMError(f"模型返回不是 JSON 对象：{cleaned[:120]}") from exc
    if not isinstance(payload, dict):
        raise LLMError("模型返回的 JSON 顶层必须是对象")
    return payload


class LLMClient:
    """OpenAI 兼容的 chat/completions JSON 客户端。"""

    def __init__(self, key: str | None = None, base: str | None = None, model: str | None = None,
                 timeout: float | None = None, max_retries: int = 2):
        self._key = (key if key is not None else api_key())
        self.base = (base or base_url()).rstrip("/")
        self.model = (model or model_name())
        self.timeout = timeout if timeout is not None else _timeout()
        self.max_retries = max(0, int(max_retries))
        if not self._key:
            raise MissingKeyError(
                "live 模式需要模型密钥：请在环境变量或项目 .env 里设置 "
                + " 或 ".join(KEY_ENV_NAMES) + "（拒绝静默降级为离线规则）"
            )

    def describe(self) -> dict:
        """可安全外发的运行信息——不含密钥。"""
        return {"model": self.model, "base_url": self.base, "key_present": bool(self._key)}

    # ---------- HTTP ----------
    def _post(self, body: dict, tag: str) -> dict:
        request = urllib.request.Request(
            f"{self.base}/chat/completions",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._key}",
                # 部分网关（Cloudflare 1010）会拦截默认的 Python-urllib UA，必须显式声明
                "User-Agent": os.environ.get("DIRECTOR_LLM_USER_AGENT", USER_AGENT),
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise LLMError(f"模型接口返回 HTTP {exc.code}（tag={tag}）：{detail}") from exc
        except urllib.error.URLError as exc:
            raise LLMError(f"无法连接模型接口（tag={tag}）：{exc.reason}") from exc
        except (TimeoutError, json.JSONDecodeError) as exc:
            raise LLMError(f"模型接口响应异常（tag={tag}）：{type(exc).__name__}") from exc

    def chat_json(self, system_prompt: str, user_prompt: str, tag: str = "",
                  temperature: float | None = None) -> dict:
        """要求模型返回 JSON 对象；失败重试，最终抛 LLMError（不返回兜底假数据）。"""
        body: dict = {
            "model": self.model,
            "messages": [{"role": "system", "content": system_prompt},
                         {"role": "user", "content": user_prompt}],
            "response_format": {"type": "json_object"},
        }
        if temperature is not None:
            body["temperature"] = temperature

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 2):
            started = time.time()
            try:
                data = self._post(body, tag)
            except LLMError as exc:
                last_error = exc
                # 部分兼容端点不支持 response_format：去掉后重试一次
                if "HTTP 400" in str(exc) and "response_format" in body:
                    body.pop("response_format", None)
                    continue
                time.sleep(min(2.0, 0.5 * attempt))
                continue
            try:
                content = data["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as exc:
                last_error = LLMError(f"模型响应缺少 choices/message（tag={tag}）")
                time.sleep(min(2.0, 0.5 * attempt))
                continue
            try:
                parsed = parse_json_object(content)
            except LLMError as exc:
                last_error = exc
                time.sleep(min(2.0, 0.5 * attempt))
                continue
            parsed["_usage"] = data.get("usage", {})
            parsed["_latency"] = round(time.time() - started, 3)
            parsed["_attempts"] = attempt
            parsed["_tag"] = tag
            parsed["_model"] = data.get("model", self.model)
            parsed["_raw"] = str(content)[:2000]
            return parsed
        raise LLMError(f"模型调用失败（tag={tag}，尝试 {self.max_retries + 1} 次）：{last_error}")
