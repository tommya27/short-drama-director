"""Portable scene specifications and complete isolated world snapshots."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import uuid
import copy
import random


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@dataclass
class SceneSpec:
    title: str
    genre: str = "职场悬疑"
    location: str = "董事会会议室"
    goal: str = "判断财务造假指控是否进入正式调查"
    characters: list[dict[str, Any]] = field(default_factory=list)
    items: list[dict[str, Any]] = field(default_factory=list)
    facts: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "genre": self.genre,
            "location": self.location,
            "goal": self.goal,
            "characters": self.characters,
            "items": self.items,
            "facts": self.facts,
        }


def default_boardroom_spec(title: str = "董事会：未签字的授权记录") -> SceneSpec:
    return SceneSpec(
        title=title,
        characters=[
            {"id": "ceo", "name": "顾沉", "role": "CEO", "location": "董事会会议室", "stage_position": "主位", "goal": "守住职位并争取时间"},
            {"id": "cfo", "name": "林岚", "role": "财务总监", "location": "董事会会议室", "stage_position": "投影屏旁", "goal": "让调查正式立项"},
            {"id": "legal", "name": "周衡", "role": "法务负责人", "location": "董事会会议室", "stage_position": "文件柜旁", "goal": "确认证据链是否完整"},
            {"id": "chair", "name": "沈董事长", "role": "董事长", "location": "董事会会议室", "stage_position": "主持位", "goal": "在不失控的情况下作出决定"},
        ],
        items=[
            {"id": "contract", "name": "供应商合同", "location": "投影屏", "holder": "cfo"},
            {"id": "email", "name": "授权邮件打印件", "location": "文件夹", "holder": "legal"},
            {"id": "usb", "name": "审计U盘", "location": "林岚的公文包", "holder": "cfo"},
        ],
        facts=[
            {"id": "fact_contract", "label": "合同金额在三个月内连续上调", "known_by": ["cfo", "legal"], "source": "供应商合同第4页"},
            {"id": "fact_email", "label": "授权邮件没有董事长的数字签名", "known_by": ["legal"], "source": "法务归档邮件"},
            {"id": "fact_usb", "label": "审计U盘包含原始付款流水", "known_by": ["cfo"], "source": "外部审计交接单"},
            {"id": "fact_secret", "label": "董事长尚未看到完整付款流水", "known_by": ["ceo", "cfo", "legal", "chair"], "source": "导演设定"},
        ],
    )


def default_state(spec: dict[str, Any]) -> dict[str, Any]:
    spec = normalize_spec(spec)
    return {
        "step": 0,
        "actors": {a["id"]: {"location": a["location"], "status": "active", "health": 100,
                               "observation_ids": [], "diaries": [], "action_history": []}
                   for a in spec["characters"]},
        "items": {i["id"]: dict(copy.deepcopy(i), state=i.get("state", "active"),
                                 holder=i.get("holder"), location=None if i.get("holder") else i.get("location"))
                  for i in spec.get("items", [])},
        "facts": copy.deepcopy(spec.get("facts", [])),
        "events": [],
        "event_counter": 0,
        "rng_state": random.Random(spec.get("rng_seed", 42)).getstate(),
        "directives": [],
        "locked_fact_ids": [],
        "config_version": 1,
    }


def normalize_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Validate portable input while retaining complete cards and template data."""
    if not isinstance(spec, dict):
        raise ValueError('场景必须是对象')
    result = copy.deepcopy(spec)
    result.setdefault('title', '未命名场景')
    result.setdefault('location', '现场')
    result.setdefault('characters', [])
    result.setdefault('items', [])
    result.setdefault('facts', [])
    for field in ('title', 'location'):
        if not isinstance(result[field], str) or not result[field].strip():
            raise ValueError(f'{field} 必须是非空字符串')
    for field in ('goal', 'genre', 'public_canon', 'premise', 'conflict'):
        if field in result and not isinstance(result[field], str):
            raise ValueError(f'{field} 必须是字符串')
    for field in ('goals', 'relationships'):
        if field in result and (not isinstance(result[field], list)
                or any(not isinstance(value, str) for value in result[field])):
            raise ValueError(f'{field} 必须是字符串数组')
    if 'scene_manifest' in result and not isinstance(result['scene_manifest'], dict):
        raise ValueError('scene_manifest 必须是对象')
    if 'author_facts' in result and (not isinstance(result['author_facts'],list)
            or any(not isinstance(value,(str,dict)) for value in result['author_facts'])):
        raise ValueError('author_facts 必须是事实数组')
    for field in ('characters', 'items', 'facts'):
        if not isinstance(result[field], list):
            raise ValueError(f'{field} 必须是数组')
    if not result['characters']:
        raise ValueError('场景至少需要一个角色')
    seen = set()
    for actor in result['characters']:
        if not isinstance(actor, dict) or not isinstance(actor.get('id'), str) or not actor['id'].strip():
            raise ValueError('角色必须提供非空 id')
        if actor['id'] in seen:
            raise ValueError('角色 id 重复')
        seen.add(actor['id'])
        actor.setdefault('name', actor['id'])
        actor.setdefault('location', actor.get('start_location', result['location']))
        actor.setdefault('start_location', actor['location'])
        actor.setdefault('public_identity', actor.get('role', '角色'))
        actor.setdefault('true_identity', actor['public_identity'])
        actor.setdefault('hidden_goal', actor.get('goal', ''))
        actor.setdefault('secret', '')
        actor.setdefault('personality', '')
        actor.setdefault('combat', 0)
        for field in ('name', 'location', 'public_identity', 'true_identity', 'hidden_goal', 'secret', 'personality'):
            if not isinstance(actor[field], str):
                raise ValueError(f'角色 {field} 必须是字符串')
        if not actor['name'].strip() or not actor['location'].strip():
            raise ValueError('角色名称和地点不能为空')
    world = result.setdefault('world', {})
    if not isinstance(world, dict):
        raise ValueError('world 必须是对象')
    world.setdefault('name', result['location'])
    world.setdefault('setting', result.get('goal', ''))
    world.setdefault('locations', list(dict.fromkeys([result['location']] + [a['location'] for a in result['characters']])))
    world.setdefault('connections', {})
    for field in ('name', 'setting', 'deadline_hint'):
        if field in world and not isinstance(world[field], str):
            raise ValueError(f'world.{field} 必须是字符串')
    if (not isinstance(world['locations'], list)
            or any(not isinstance(location, str) or not location for location in world['locations'])):
        raise ValueError('world.locations 必须是非空地点字符串数组')
    if not isinstance(world['connections'], dict):
        raise ValueError('world.connections 必须是对象')
    for location, targets in world['connections'].items():
        if location not in world['locations'] or not isinstance(targets, list) or any(t not in world['locations'] for t in targets):
            raise ValueError('地点连通关系必须引用合法地点')
    if not world['locations'] or any(a['location'] not in world['locations'] for a in result['characters']):
        raise ValueError('角色初始地点必须属于 world.locations')
    for field in ('items', 'facts'):
        ids = set()
        for value in result[field]:
            if not isinstance(value, dict) or not isinstance(value.get('id'), str) or not value['id']:
                raise ValueError(f'{field} 必须提供非空 id')
            if value['id'] in ids:
                raise ValueError(f'{field} id 重复')
            ids.add(value['id'])
            if field == 'items':
                if value.get('state', 'active') not in ('active', 'destroyed'):
                    raise ValueError('道具 state 必须是 active 或 destroyed')
                if 'name' in value and not isinstance(value['name'], str):
                    raise ValueError('道具 name 必须是字符串')
                if 'aliases' in value and (not isinstance(value['aliases'], list)
                                          or any(not isinstance(a, str) for a in value['aliases'])):
                    raise ValueError('道具 aliases 必须是字符串数组')
            if field == 'facts':
                value.setdefault('known_by', [])
                if value.get('public') is True:
                    value['known_by'] = sorted(seen)
                if not isinstance(value['known_by'], list) or any(not isinstance(v, str) for v in value['known_by']):
                    raise ValueError('known_by 必须是角色 id 数组')
                if any(actor_id not in seen for actor_id in value['known_by']):
                    raise ValueError('事实引用不存在的知情角色')
                for text_field in ('label', 'source'):
                    if text_field in value and not isinstance(value[text_field], str):
                        raise ValueError(f'事实 {text_field} 必须是字符串')
            elif value.get('state') == 'destroyed':
                if value.get('holder') is not None or value.get('location') is not None:
                    raise ValueError('已销毁道具不能有持有者或地点')
            elif value.get('holder'):
                if not isinstance(value['holder'], str):
                    raise ValueError('道具 holder 必须是角色 id')
                if value['holder'] not in seen:
                    raise ValueError('道具持有者不存在')
                value['location'] = None
            else:
                value.setdefault('location', result['location'])
                if not isinstance(value['location'], str):
                    raise ValueError('道具 location 必须是地点字符串')
                if value['location'] not in world['locations']:
                    raise ValueError('道具地点必须属于 world.locations')
    return result
