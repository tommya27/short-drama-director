"""开场生成：把作者一句话想法扩写为可确认的完整设定（人物 / 地点 / 道具 / 事实 / 舞台 manifest）。

两条路径，界面会如实标注来源：
- **模型路径**（live 模式且有密钥）：让真实模型按严格 JSON 结构产出开场，含舞台 manifest
  （palette / zones / asset_set / camera_presets / interaction_points）。
- **规则路径**（离线或无密钥，或模型输出不可用时回退）：本地确定性模板，永不联网。

回退是**显式**的：返回值里的 `source` 字段会告诉界面这份开场是谁生成的，不做静默替换。
"""
from __future__ import annotations

import json
import os
from typing import Any

from .llm_client import LLMClient, MissingKeyError
from .models import normalize_spec
from .scene_input import portable_spec, public_spec

#: 3D/2.5D 舞台能直接渲染的道具名（模型只能从这个词表里选，避免生成渲染不了的资产）
ASSET_VOCABULARY = ("table", "chairs", "screen", "cabinet", "plants",
                    "bench", "pole", "counter", "desk", "bed",
                    "outdoor", "street", "vehicle", "cave", "rock", "pine", "rail", "console",
                    "pillars", "lamp", "window_strip",
                    "timber", "track", "minecart", "lantern", "tunnel", "debris",
                    "sofa", "shelf", "crate", "barrel", "gate", "door", "car", "podium")

OPENING_SYSTEM = f"""你是短剧的前期策划，把作者的一句话想法扩写成可以直接开演的设定。
只能输出 JSON 对象，不要解释。字段：
{{
  "title": "不超过 20 字的剧名",
  "genre": "短剧类型，如 都市/悬疑/武侠/科幻",
  "location": "这场戏的主场地，一个具体地点名",
  "locations": ["该场地的 3-4 个可区分区域，例如 会议室/走廊/茶水间；或 山门/石阶/崖边"],
  "world_setting": "两三句话的世界与情境设定",
  "conflict": "本场戏的核心冲突，一句话",
  "characters": [
    {{"id": "英文小写 id", "name": "中文姓名", "role": "protagonist 或 antagonist 或 supporting",
      "goal": "公开目标", "hidden_goal": "隐藏目标", "secret": "不为人知的秘密",
      "public_identity": "公开身份", "true_identity": "真实身份（可与公开身份相同）",
      "location": "开场所在区域（必须在 locations 里）", "gender": "男/女",
      "appearance": "外形特征，用于生成定妆照", "behavior_anchor": "行为特征",
      "combat": 1-10 的整数, "personality": "性格", "possessions": "随身物品描述"}}
  ],
  "items": [{{"id": "英文小写 id", "name": "道具名", "holder": "角色 id 或 null", "location": "所在地点"}}],
  "facts": [{{"id": "英文小写 id", "label": "事实描述", "known_by": ["角色 id"], "source": "作者设定 或 剧中线索"}}],
  "scene_manifest": {{
    "scene_key": "英文小写场景类型，如 boardroom/office/cafe/hospital/classroom/inn/mansion/mountain/ship/subway/street/generic",
    "name": "场景类型中文名，如 山巅 / 游轮驾驶舱",
    "renderer_type": "generic3d",
    "palette": {{"floor": "#rrggbb", "wall": "#rrggbb", "wood": "#rrggbb", "accent": "#rrggbb"}},
    "zones": [{{"id": "区域名，必须与 locations 完全一致", "position": [x, 0, z]}}],
    "asset_set": ["只能从此表选择：{", ".join(ASSET_VOCABULARY)}"],
    "camera_presets": ["wide", "top", "focus"],
    "interaction_points": [{{"id": "英文 id", "label": "中文标签", "position": [x, y, z], "item_id": "可选，对应道具 id"}}]
  }}
}}
要求：
1. characters 给 3-4 个，立场要真正冲突；只能有一个 protagonist。
2. locations 与 zones 的区域名必须一致；zone 坐标 x∈[-6,6]、z∈[-5,5]，彼此不要重叠。
3. 按场景选形态标记，必须放进 asset_set：
   - 户外自然（山、林、海、街外）："outdoor"；配 rock / pine / rail。
   - 矿洞/地道/隧道/地窖/墓道/洞穴：**必须用 "cave"**；配 timber / track / minecart / lantern / tunnel / debris / rock。
     这类场景**禁止**出现 pine 或会议桌——矿洞里不能有松树和办公家具。
   - 交通载具（地铁、火车、船、车、飞机、驾驶舱）："vehicle"；配 bench / pole / console / rail / window_strip。
   - 街头广场（城市街道、广场、码头）："street"；配 lamp / pillars / rail。
   - 咖啡/餐厅/酒吧：配 counter / table / chairs / lamp。
   - 医院/诊所：配 bed / cabinet；教室/学校：配 desk / chairs / screen。
   - 会议室/办公室：配 table / chairs / screen / cabinet / plants / door。
   - 家里/公寓/客厅：配 sofa / table / cabinet / door / plants。
   - 仓库/工地/厂房/停车场：配 crate / barrel / gate / timber / rail / car。
   - 店铺/超市/药房：配 shelf / counter / door。
   - 发布会/法庭/礼堂/教室：配 podium / chairs / desk / screen / pillars。
   零件要用得上就写进 asset_set；同一场景一般 3-6 个零件即可，不要堆砌。
   同一个 asset_set 里不要同时出现 outdoor 和 vehicle、outdoor 和 cave；不要给地铁、车厢这类场景配会议桌。
4. 只写这场戏真正用得上的 2-4 个道具、2-4 条事实。
5. 用中文写作正文，id 用英文小写。"""


def _with_template_drama(spec: dict) -> dict:
    """规则路径也要有契约与节拍：用模板补齐，绝不联网。"""
    from .dramatic import ensure_dramatic
    result = ensure_dramatic(dict(spec), use_model=False)
    result['dramatic_source'] = {'contract': 'template', 'beats': 'template'}
    return result


def model_available() -> bool:
    from .llm_client import api_key
    return bool(api_key())


def _coerce_manifest(raw: Any) -> dict:
    """只保留前端与 3D 渲染器认识的字段。"""
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    for key in ("scene_key", "name", "renderer_type"):
        if isinstance(raw.get(key), str) and raw[key].strip():
            out[key] = raw[key].strip()
    palette = raw.get("palette")
    if isinstance(palette, dict):
        colors = {k: v for k, v in palette.items()
                  if k in ("floor", "wall", "wood", "accent") and isinstance(v, str)}
        if colors:
            out["palette"] = colors
    zones = []
    for zone in raw.get("zones") or []:
        if isinstance(zone, dict) and isinstance(zone.get("id"), str) and isinstance(zone.get("position"), list) \
                and len(zone["position"]) == 3 and all(isinstance(n, (int, float)) for n in zone["position"]):
            zones.append({"id": zone["id"], "position": [float(n) for n in zone["position"]]})
    if zones:
        out["zones"] = zones
    assets = [name for name in (raw.get("asset_set") or []) if name in ASSET_VOCABULARY]
    if assets:
        out["asset_set"] = sorted(set(assets), key=ASSET_VOCABULARY.index)
    cameras = [c for c in (raw.get("camera_presets") or []) if isinstance(c, str)]
    if cameras:
        out["camera_presets"] = cameras
    points = []
    for point in raw.get("interaction_points") or []:
        if isinstance(point, dict) and isinstance(point.get("id"), str) and isinstance(point.get("position"), list) \
                and len(point["position"]) == 3 and all(isinstance(n, (int, float)) for n in point["position"]):
            entry = {"id": point["id"], "label": str(point.get("label") or point["id"]),
                     "position": [float(n) for n in point["position"]]}
            if isinstance(point.get("item_id"), str):
                entry["item_id"] = point["item_id"]
            points.append(entry)
    if points:
        out["interaction_points"] = points
    return out


def expand_with_model(premise: str, client: LLMClient | None = None) -> dict:
    """用真实模型生成开场设定；输出不合法时抛异常，由调用方决定回退。"""
    client = client or LLMClient()
    data = client.chat_json(OPENING_SYSTEM, f"作者的想法：{premise}\n请扩写这场戏。", tag="opening_expand")
    manifest = _coerce_manifest(data.get("scene_manifest"))
    characters = data.get("characters")
    if not isinstance(characters, list) or len(characters) < 2:
        raise ValueError("模型没有给出足够的角色")
    locations = [x for x in (data.get("locations") or []) if isinstance(x, str) and x.strip()]
    if not locations:
        raise ValueError("模型没有给出地点")
    spec = {
        "title": str(data.get("title") or premise[:20]),
        "genre": str(data.get("genre") or "短剧"),
        "location": str(data.get("location") or locations[0]),
        "locations": locations,
        "conflict": str(data.get("conflict") or premise),
        "characters": characters,
        "items": data.get("items") if isinstance(data.get("items"), list) else [],
        "facts": data.get("facts") if isinstance(data.get("facts"), list) else [],
        "scene_manifest": manifest,
    }
    verified = portable_spec(spec)
    from .dramatic import ensure_dramatic
    verified = ensure_dramatic(verified, use_model=True, client=client)
    world = verified.get("world") or {}
    world.setdefault("locations", locations)
    world.setdefault("connections", {})
    world.setdefault("name", verified.get("location", locations[0]))
    world.setdefault("setting", str(data.get("world_setting") or premise))
    verified["world"] = world
    verified["premise"] = premise
    verified["goal"] = str(data.get("goal") or "让角色在这场戏里做出影响冲突的选择")
    return verified


def expand(premise: str, client: LLMClient | None = None) -> dict:
    """返回 {premise, questions, scene_spec, source}。source 为 llm 或 rule，界面据此标注。"""
    if not premise.strip():
        raise ValueError("想法不能为空")
    if os.environ.get("DIRECTOR_OPENING_MODE", "").strip().lower() == "rule" or not model_available():
        from .scene_input import expand as expand_rule
        result = expand_rule(premise)
        result["source"] = "rule"
        result["scene_spec"] = _with_template_drama(result.get("scene_spec") or {})
        return result
    try:
        spec = expand_with_model(premise, client)
    except Exception as exc:  # noqa: BLE001 - 任何失败都回退规则路径，并如实标注来源与原因
        from .scene_input import expand as expand_rule
        result = expand_rule(premise)
        result["source"] = "rule"
        result["fallback_reason"] = f"{type(exc).__name__}: {exc}"[:200]
        result["scene_spec"] = _with_template_drama(result.get("scene_spec") or {})
        return result
    return {
        "premise": premise,
        "questions": ["谁最想得到什么？", "谁知道别人不知道的信息？", "哪一个道具会改变选择？"],
        "scene_spec": public_spec(spec),
        "source": "llm",
    }
