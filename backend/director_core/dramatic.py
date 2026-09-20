"""剧情结构层：本场戏契约、5 节拍计划、剧情检查、可读剧本渲染。

设计原则（用户确定）：
- **规划器只定义"这一阶段需要解决什么问题"**；角色 Agent 仍然自己提出行动，不被写成念台词。
- 检查只**提示**，不替作者否决剧情；所有结论都能指到具体事件或字段。
- 结构与检查尽量**确定性**（可复现、可测试）；模型只用于生成契约与节拍文本，且失败即回退模板。
"""
from __future__ import annotations

import json
import re
from typing import Any

#: 5 节拍模板：每个节拍回答"这一段要解决什么问题"，并给出可观察的完成信号
BEAT_TEMPLATE: list[dict[str, Any]] = [
    {"beat_id": "beat_1_open", "purpose": "开场状态", "pressure": "交代谁想要什么、谁挡着谁",
     "information_change": "观众知道的信息差被建立", "completion_signal": "每个角色都表明立场或意图"},
    {"beat_id": "beat_2_pressure", "purpose": "第一次施压", "pressure": "有人主动出手，目标受到阻力",
     "information_change": "出现第一个可核对的事实或证据", "completion_signal": "至少一次行动被对方明确阻挡或反击"},
    {"beat_id": "beat_3_shift", "purpose": "信息或关系变化", "pressure": "局面因新信息而改变",
     "information_change": "有人知道了原本不知道的事（或被迫披露）", "completion_signal": "know-how 集合发生变化，或道具归属/位置改变"},
    {"beat_id": "beat_4_choice", "purpose": "关键选择", "pressure": "主角必须在代价之间选一个",
     "information_change": "选择本身暴露了立场", "completion_signal": "主角做出一个不可逆的选择（交出道具/放弃目标/当场摊牌）"},
    {"beat_id": "beat_5_result", "purpose": "结果或悬念", "pressure": "代价兑现，或留下新问题",
     "information_change": "required_change 发生，或留下新的未知", "completion_signal": "契约里的 required_change 达成，或产生新的悬念点"},
]

CONTRACT_FIELDS = ("protagonist", "scene_goal", "opposing_force", "stakes",
                   "central_secret", "required_change", "ending_condition")

CONTRACT_SYSTEM = """你是短剧的戏剧构作。只输出 JSON 对象，不要解释。字段：
{
  "protagonist": "主角的角色 id",
  "scene_goal": "主角在这场戏里要达成的具体目标（一句话）",
  "opposing_force": "阻止他的角色 id",
  "stakes": "失败的代价，具体到会失去什么",
  "central_secret": "这场戏围绕的秘密（一句话）",
  "required_change": "这场戏结束时必须发生的变化（可观察）",
  "ending_condition": "判定这场戏结束的条件（可观察）"
}
要求：主角与对手的目标必须**互相阻碍**；stakes 与 required_change 必须能在画面里看见。"""

BEAT_SYSTEM = """你是短剧的节奏设计。基于契约给出 5 个剧情节拍，只输出 JSON：
{"beats":[{"beat_id":"英文 id","purpose":"中文 4-6 字","pressure":"这一段施加什么压力",
"information_change":"这一段必须发生的信息变化","completion_signal":"怎么算这一段完成（可观察）"}]}
要求：必须正好 5 个；pressure 逐拍升级；第 4 拍必须是主角的关键选择；第 5 拍必须兑现或留下悬念。"""


def _field(spec: dict, *names, default=""):
    for name in names:
        value = spec.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return default


def actors_of(spec: dict) -> list[dict]:
    return list(spec.get("characters") or spec.get("actors") or [])


def _pick(actors: list[dict], role: str) -> dict | None:
    return next((actor for actor in actors if actor.get("role") == role), None)


# ---------- 契约 ----------

def build_contract(spec: dict) -> dict[str, str]:
    """确定性兜底契约：从场景设定直接推导，保证任何场景都有一份可用契约。"""
    actors = actors_of(spec)
    protagonist = _pick(actors, "protagonist") or (actors[0] if actors else {})
    antagonist = _pick(actors, "antagonist") or next(
        (a for a in actors if a.get("id") != protagonist.get("id")), protagonist)
    secret_holder = next((a for a in actors if a.get("secret")), None)
    goal = _field(spec, "goal", "conflict") or "在这场戏里争到自己要的东西"
    return {
        "protagonist": str(protagonist.get("id", "")),
        "scene_goal": _field(protagonist, "goal", default=goal),
        "opposing_force": str(antagonist.get("id", "")),
        "stakes": _field(protagonist, "stakes", default=f"如果失败，{protagonist.get('name', '主角')}会失去{goal}"),
        "central_secret": str((secret_holder or {}).get("secret", "")) or _field(spec, "conflict", default="场上有一个人没说真话"),
        "required_change": _field(spec, "required_change", default="有人当众改变了立场或交出了关键信息"),
        "ending_condition": _field(spec, "ending_condition", default="主角的选择产生可见后果，或留下明确的悬念"),
    }


def contract_with_model(spec: dict, client=None) -> dict[str, str]:
    from .llm_client import LLMClient
    client = client or LLMClient()
    payload = {"title": spec.get("title"), "location": spec.get("location"),
               "conflict": spec.get("conflict"), "goal": spec.get("goal"),
               "characters": [{k: a.get(k) for k in ("id", "name", "role", "goal", "hidden_goal", "secret")}
                              for a in actors_of(spec)]}
    data = client.chat_json(CONTRACT_SYSTEM, json.dumps(payload, ensure_ascii=False), tag="dramatic_contract")
    contract = build_contract(spec)
    for key in CONTRACT_FIELDS:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            contract[key] = value.strip()
    ids = {a.get("id") for a in actors_of(spec)}
    if contract["protagonist"] not in ids:
        contract["protagonist"] = build_contract(spec)["protagonist"]
    if contract["opposing_force"] not in ids or contract["opposing_force"] == contract["protagonist"]:
        fallback = build_contract(spec)
        contract["opposing_force"] = fallback["opposing_force"]
    return contract


# ---------- 节拍 ----------

def default_beats() -> list[dict[str, Any]]:
    return [dict(beat) for beat in BEAT_TEMPLATE]


def beats_with_model(spec: dict, contract: dict, client=None) -> list[dict[str, Any]]:
    from .llm_client import LLMClient
    client = client or LLMClient()
    prompt = json.dumps({"contract": contract, "location": spec.get("location"),
                         "characters": [{"id": a.get("id"), "name": a.get("name"), "role": a.get("role")}
                                        for a in actors_of(spec)]}, ensure_ascii=False)
    data = client.chat_json(BEAT_SYSTEM, prompt, tag="dramatic_beats")
    raw = data.get("beats")
    if not isinstance(raw, list) or len(raw) != 5:
        raise ValueError("节拍必须是 5 个")
    beats = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError("节拍必须是对象")
        template = BEAT_TEMPLATE[index]
        beats.append({
            "beat_id": str(item.get("beat_id") or template["beat_id"]),
            "purpose": str(item.get("purpose") or template["purpose"])[:20],
            "pressure": str(item.get("pressure") or template["pressure"])[:80],
            "information_change": str(item.get("information_change") or template["information_change"])[:80],
            "completion_signal": str(item.get("completion_signal") or template["completion_signal"])[:80],
        })
    return beats


def plan_beats(spec: dict, contract: dict, client=None) -> list[dict[str, Any]]:
    """模型可用则用模型，否则回退模板——回退不等于失败，界面仍能显示节拍。"""
    try:
        return beats_with_model(spec, contract, client)
    except Exception:  # noqa: BLE001 - 任何失败都回退模板
        return default_beats()


def ensure_dramatic(spec: dict, *, use_model: bool = True, client=None) -> dict:
    """确保场景带 contract 与 beats（幂等）：已有就沿用。

    同时记录 dramatic_source：**如实标注每一项是真模型生成还是模板回退**，
    供界面显示，避免把模板当成模型产出。
    """
    result = dict(spec)
    source = dict(result.get("dramatic_source") or {})
    source.setdefault("contract", "template")
    source.setdefault("beats", "template")
    contract = result.get("contract")
    if not isinstance(contract, dict) or not contract.get("protagonist"):
        contract = None
        if use_model:
            try:
                contract = contract_with_model(result, client)
                source["contract"] = "llm"
            except Exception:  # noqa: BLE001
                contract = None
        contract = contract or build_contract(result)
    result["contract"] = {key: str(contract.get(key, "") or "") for key in CONTRACT_FIELDS}
    beats = result.get("beats")
    if not isinstance(beats, list) or len(beats) != 5:
        beats = None
        if use_model:
            try:
                beats = beats_with_model(result, result["contract"], client)
                source["beats"] = "llm"
            except Exception:  # noqa: BLE001
                beats = None
        beats = beats or default_beats()
    result["beats"] = beats
    result["dramatic_source"] = source
    return result


def beat_at(state: dict, beats: list[dict]) -> dict:
    index = int((state.get("beat_state") or {}).get("index", 0))
    index = max(0, min(index, len(beats) - 1))
    return beats[index]


# ---------- 剧情检查 ----------

def _ids(values) -> set[str]:
    return {str(v) for v in (values or [])}


def assess(spec: dict, state: dict, events: list[dict], *, contract: dict | None = None,
           beats: list[dict] | None = None, previous_tension: int = 0) -> dict:
    """7 项剧情检查：只给结论与建议，不修改任何事件。"""
    contract = contract or spec.get("contract") or build_contract(spec)
    beats = beats or spec.get("beats") or default_beats()
    beat_state = state.get("beat_state") or {}
    beat = beat_at(state, beats)
    events = [e for e in events if isinstance(e, dict)]
    checks: list[dict[str, str]] = []
    warnings: list[str] = []

    protagonist = str(contract.get("protagonist", ""))
    opponent = str(contract.get("opposing_force", ""))
    goals = {a.get("id"): (a.get("hidden_goal") or a.get("goal") or "") for a in actors_of(spec)}

    # 1 冲突：主角与对手是否互相阻碍
    if protagonist and opponent and goals.get(protagonist) and goals.get(opponent):
        checks.append({"item": "冲突", "status": "通过",
                       "detail": "主角与对手各有目标，且指向同一件事"})
    else:
        checks.append({"item": "冲突", "status": "偏弱", "detail": "缺少明确对手或目标"})
        warnings.append("契约里没有互相对立的目标，这一场容易变成聊天。")

    # 2 推进：本轮是否有事件真正改变状态
    acted = {str(e.get("actor_id")) for e in events}
    if events:
        checks.append({"item": "推进", "status": "通过" if len(acted) >= 2 else "偏弱",
                       "detail": f"本步有 {len(events)} 个行动，来自 {len(acted)} 个角色"})
    else:
        checks.append({"item": "推进", "status": "未发生", "detail": "本步没有候选行动"})
        warnings.append("本步没有行动，无法推进。")

    # 3 信息变化：有没有人知道得更多，或被迫披露
    revealed = [e for e in events if (e.get("revealed_information") or e.get("reveal_fact_ids"))]
    info_delta = any(e.get("tension_delta", 0) and e.get("revealed_information") for e in events)
    if revealed or info_delta:
        checks.append({"item": "信息变化", "status": "通过",
                       "detail": f"本步披露了 {len(revealed)} 处信息"})
    else:
        checks.append({"item": "信息变化", "status": "未发生", "detail": "没有人获得新信息"})
        if beat["beat_id"].endswith(("shift", "choice")):
            warnings.append("这一拍要求信息变化，但本步没有披露或发现。")

    # 4 因果：是否回应了前面的事件
    known_ids = {str(e.get("id")) for e in state.get("events", []) if isinstance(e, dict)}
    causal = [e for e in events if _ids(e.get("caused_by_event_ids")) & known_ids]
    if causal:
        checks.append({"item": "因果关系", "status": "通过",
                       "detail": f"{len(causal)} 个行动明确回应了此前的事件"})
    elif events and known_ids:
        checks.append({"item": "因果关系", "status": "偏弱", "detail": "本步没有 action 回应上一事件"})
        warnings.append("角色在自说自话：没有行动引用此前事件。")
    else:
        checks.append({"item": "因果关系", "status": "未发生", "detail": "尚无历史事件可回应"})

    # 5 升级：张力是否不低于上一拍
    tension = max([int(e.get("tension_delta", 0) or 0) for e in events] or [0])
    if tension > previous_tension:
        checks.append({"item": "压力升级", "status": "通过", "detail": f"张力 {previous_tension} → {tension}"})
    elif tension == previous_tension and events:
        checks.append({"item": "压力升级", "status": "未发生", "detail": f"张力维持 {tension}"})
        warnings.append("压力没有升级，观众会觉得在原地打转。")
    else:
        checks.append({"item": "压力升级", "status": "未发生", "detail": "本步张力低于上一拍"})
        warnings.append("压力下降了，考虑让对手加码。")

    # 6 人物主动性：主角是否自己做出选择
    protagonist_acted = any(str(e.get("actor_id")) == protagonist for e in events)
    if protagonist_acted:
        checks.append({"item": "人物主动性", "status": "通过", "detail": "主角本步主动出手"})
    else:
        checks.append({"item": "人物主动性", "status": "偏弱", "detail": "主角本步没有行动，被剧情推着走"})
        warnings.append("可以让主角提一个必须当场回答的问题。")

    # 7 可拍性：动作/道具/位置是否具体
    playable = [e for e in events if str(e.get("action") or "").strip() and str(e.get("location") or "").strip()]
    if playable:
        checks.append({"item": "可拍性", "status": "通过",
                       "detail": f"{len(playable)} 个行动带明确动作与地点"})
    else:
        checks.append({"item": "可拍性", "status": "偏弱", "detail": "缺少可表演的实体动作"})
        warnings.append("把心理活动改成能演出来的动作（拿起、推过去、站起来）。")

    # 8 结尾准备
    required = str(contract.get("required_change", ""))
    done = bool(beat_state.get("completed_beats")) and str(beat.get("beat_id", "")).endswith("result")
    if done or (required and any(required[:6] and required[:6] in str(e.get("consequence") or "") for e in events)):
        checks.append({"item": "结尾准备", "status": "通过", "detail": "已具备收束条件"})
    else:
        checks.append({"item": "结尾准备", "status": "尚未满足",
                       "detail": f"还差：{contract.get('ending_condition', '')[:40]}"})

    passed = sum(1 for c in checks if c["status"] == "通过")
    return {
        "beat": beat,
        "beat_index": int(beat_state.get("index", 0)),
        "beat_total": len(beats),
        "tension": tension,
        "checks": checks,
        "warnings": warnings,
        "passed": passed,
        "total": len(checks),
        "suggestion": warnings[0] if warnings else _next_beat_suggestion(beat),
    }


def advance_beat_state(state: dict, beats: list[dict], *, tension: int = 0) -> dict:
    """把当前拍标记完成并推进到下一拍（由作者触发，不由系统自动推进）。"""
    beat_state = dict(state.get("beat_state") or {})
    index = max(0, min(int(beat_state.get("index", 0)), max(0, len(beats) - 1)))
    completed = list(beat_state.get("completed_beats") or [])
    if beats and index < len(beats) - 1:
        current = str(beats[index].get("beat_id", f"beat_{index + 1}"))
        if current not in completed:
            completed.append(current)
        index += 1
    beat_state.update(index=index, completed_beats=completed,
                      tension=max(int(beat_state.get("tension", 0) or 0), int(tension or 0)),
                      updated_by="author")
    state["beat_state"] = beat_state
    return state


def _next_beat_suggestion(beat: dict) -> str:
    return f"这一段要解决：{beat.get('information_change', '')}；完成信号：{beat.get('completion_signal', '')}"


# ---------- 可读剧本 ----------

def _speaker(spec: dict, actor_id: str) -> str:
    for actor in actors_of(spec):
        if actor.get("id") == actor_id:
            return str(actor.get("name") or actor_id)
    return str(actor_id or "?")


def render_screenplay(spec: dict, events: list[dict]) -> str:
    """确定性渲染成可读短剧草稿（不调用模型，可复现），每段标注来源事件 ID。"""
    location = _field(spec, "location", default="现场")
    lines = [f"内景 {location} 日", ""]
    for event in events:
        if not isinstance(event, dict):
            continue
        who = _speaker(spec, str(event.get("actor_id", "")))
        action = str(event.get("action") or "").strip()
        dialogue = str(event.get("dialogue") or "").strip()
        consequence = str(event.get("consequence") or "").strip()
        # 内心活动不写成台词，作为表演提示
        if action:
            lines.append(f"{who}{action}。" if not action.startswith(who) else f"{action}。")
        if dialogue:
            lines += ["", who, dialogue, ""]
        elif action:
            lines.append("")
        if consequence:
            lines.append(f"（{consequence}）")
            lines.append("")
        lines.append(f"【来源：{event.get('id', '')}】")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def render_storyboard(spec: dict, events: list[dict]) -> list[dict]:
    """分镜草稿：镜号 / 景别 / 机位 / 画面 / 角色 / 对白 / 道具 / 节奏 / 来源事件。"""
    shots = []
    for index, event in enumerate([e for e in events if isinstance(e, dict)], start=1):
        action = str(event.get("action") or "")
        dialogue = str(event.get("dialogue") or "")
        close = bool(dialogue) or (event.get("tension_delta") or 0) >= 4
        shots.append({
            "shot": index,
            "shot_size": "近景" if close else "中景",
            "camera": "角色过肩" if dialogue else "固定机位",
            "frame": action,
            "actor": _speaker(spec, str(event.get("actor_id", ""))),
            "dialogue": dialogue,
            "props": str(event.get("transfer", {}).get("item_id", "")) if isinstance(event.get("transfer"), dict) else "",
            "rhythm": "紧张" if (event.get("tension_delta") or 0) >= 4 else "平稳",
            "source_event_id": str(event.get("id", "")),
        })
    return shots


POLISH_SYSTEM = """你是短剧编剧。把给出的场记草稿润色成可直接阅读的剧本：
1. 保持事件顺序与人物行动不变，不新增事件、不改变事实与道具归属；
2. 保留每一段的【来源：xxx】标记，且必须与原文一一对应、不得增删；
3. 可以补写表演提示（放在括号里）与更自然的口语，但不要写内心独白当台词；
4. **只输出 JSON 对象：{"text": "润色后的剧本正文"}**，正文里用换行分隔段落；
   不要解释，不要把 JSON 包在 Markdown 代码块里。"""


def polish_screenplay(spec: dict, events: list[dict], *, client=None, draft_text: str | None = None) -> dict:
    """作者显式触发时，用真实模型润色确定性草稿；失败原样返回草稿并标注原因。"""
    base = draft_text if draft_text is not None else render_screenplay(spec, events)
    source_ids = [f"【来源：{e.get('id', '')}】" for e in events if isinstance(e, dict)]
    try:
        from .llm_client import LLMClient
        client = client or LLMClient()
        result = client.chat_json(
            POLISH_SYSTEM,
            "本场契约：" + json.dumps(spec.get("contract") or {}, ensure_ascii=False)
            + chr(10) + chr(10) + "场记草稿：" + chr(10) + base,
            tag="screenplay_polish")
        text = str(result.get("text") or result.get("content") or "").strip()
        if not text:
            return {"text": base, "polished": False, "reason": "模型返回为空"}
        missing = [mark for mark in source_ids if mark and mark not in text]
        if missing:
            # 来源标记被模型丢掉时，宁可保留可追溯的草稿，也不交付无法回查的文本
            return {"text": base, "polished": False, "reason": f"润色后丢失来源标记 {len(missing)} 处"}
        return {"text": text, "polished": True}
    except Exception as exc:  # noqa: BLE001 - 润色失败不影响主流程
        return {"text": base, "polished": False, "reason": f"{type(exc).__name__}: {exc}"[:120]}


def event_fields() -> dict[str, Any]:
    """事件新增的戏剧字段与其默认值（供 sandbox 归一化时使用）。"""
    return {"intent": "", "obstacle": "", "consequence": "", "beat_id": "", "tension_delta": 0,
            "revealed_information": [], "caused_by_event_ids": []}


def normalize_event_fields(event: dict, *, default_beat: str = "") -> dict:
    for key, default in event_fields().items():
        value = event.get(key)
        if key == "tension_delta":
            try:
                event[key] = max(0, min(5, int(value)))
            except (TypeError, ValueError):
                event[key] = 0
        elif key == "revealed_information" or key == "caused_by_event_ids":
            event[key] = [str(v) for v in value] if isinstance(value, list) else []
        else:
            event[key] = str(value or default).strip() if isinstance(value, str) or value is None else str(value)
    if default_beat and not event.get("beat_id"):
        event["beat_id"] = default_beat
    return event


TENSION_WORDS = re.compile(r"逼|威胁|摊牌|揭穿|质问|冲突|动手|夺|抢|砸|拍桌|吼")
