"""Isolated shared sandbox, reusing the legacy Agent and entity state machine.

Agents decide from one committed snapshot. ``project`` arbitrates on a copy;
only the author's commit may persist it. Legacy global config is never changed.
"""
from __future__ import annotations

import copy
import json
from typing import Protocol

from .agent import Agent, WorldEngine
from .entity_state import EntityStateMachine

from .models import new_id, normalize_spec


class CandidateGenerator(Protocol):
    def propose(self, actor: dict, context: dict, state: dict) -> dict: ...


class LLMCandidateGenerator:
    """Optional injected JSON client; no dependency on the old platform."""
    def __init__(self, llm=None):
        self.llm = llm
        if llm is None:
            raise ValueError("真实模型适配器必须显式注入；离线模式不调用模型")

    def propose(self, actor: dict, context: dict, state: dict) -> dict:
        locations = [str(x) for x in ((context.get('world') or {}).get('locations') or [])]
        constraint = (f"move_to 只能填这些地点之一：{'、'.join(locations)}；填其他地点会被判为无效移动。"
                      if locations else "move_to 必须填场景中已有的地点，不确定就省略。")
        return self.llm.chat_json(
            "你是共享叙事沙盘中的一个角色。只能根据给定的个人视角行动。"
            "他人内心、秘密、未观察事件和未知事实不在你的知识范围内。"
            "只提出自己的候选行动，不能替他人决定反应或新增权威事实。"
            "返回 JSON：action(外在动作)、dialogue、inner_thought、action_type、"
            "move_to(地点，可省略)、target_id(可省略)、"
            "transfer({item_id,to_actor_id}，仅转交自己持有的道具，可省略)、"
            "pickup_item_id、drop_item_id(均可省略)、reveal_fact_ids(公开已知信息ID数组)。"
            + constraint +
            "台词可以说谎，但不会因此改变事实。"
            "dialogue 尽量不超过 40 字；想说的多就拆成两三个短句，便于逐句显示。",
            json.dumps(context, ensure_ascii=False), tag=f"narrative_decision_{actor['id']}",
        )


def _by_id(values):
    return {value['id']: value for value in values}


def _active_directives(state, actor_id, step):
    return [d for d in state.get('directives', [])
            if d.get('status', 'pending') == 'pending'
            and d.get('target_actor_id') in (None, '', actor_id)
            and int(d.get('start_step', 0)) <= step
            and (d.get('end_step') is None or step <= int(d['end_step']))]


def role_context(spec: dict, state: dict, actor_id: str) -> dict:
    """Only actual witnesses see events; arriving later cannot reveal history."""
    cards = _by_id(spec['characters'])
    card_fields = {'id', 'name', 'role', 'location', 'stage_position', 'goal', 'public_identity',
                   'true_identity', 'hidden_goal', 'secret', 'personality', 'combat',
                   'start_location', 'possessions', 'appearance', 'gender', 'target_agent',
                   'visual_anchor', 'behavior_anchor', 'narrative_weight', 'arc'}
    card = {k: copy.deepcopy(v) for k, v in cards[actor_id].items() if k in card_fields}
    actor_state = state['actors'][actor_id]
    card['location'] = actor_state['location']
    card.pop('start_location', None)
    agent = Agent(actor_id, dict(card, start_location=actor_state['location']))
    agent.health = actor_state.get('health', 100)
    agent.status = actor_state.get('status', 'active')
    visible = [e for e in state.get('events', [])
               if actor_id in e.get('observed_by', []) or e.get('actor_id') == actor_id]
    event_text = []
    for event in visible:
        legacy_event = dict(event, actor=cards.get(event.get('actor_id'), {}).get('name', event.get('actor_id')),
                            public_action=event.get('action', ''))
        text = WorldEngine._format_event_for_agent(None, legacy_event)
        if event.get('actor_id') == actor_id and event.get('inner_thought'):
            text += '（你当时的想法：' + str(event['inner_thought']) + '）'
        event_text.append(text)
    public_people = [
        {'id': c['id'], 'name': c['name'], 'public_identity': c.get('public_identity', c.get('role', ''))}
        for c in spec['characters']
        if c['id'] != actor_id and state['actors'][c['id']]['location'] == agent.location
    ]
    facts = [{k: copy.deepcopy(v) for k, v in f.items() if k in {'id', 'label', 'source', 'truth', 'value'}}
             for f in state.get('facts', []) if actor_id in f.get('known_by', [])]
    for fact in facts:
        fact.pop('known_by', None)
        fact.pop('observations', None)
    items = [dict({k: copy.deepcopy(item[k]) for k in ('name', 'state', 'holder', 'location', 'aliases') if k in item}, id=item_id)
             for item_id, item in state.get('items', {}).items()
             if item.get('holder') == actor_id or item.get('location') == agent.location]
    return {'actor': card, 'actor_state': copy.deepcopy(actor_state),
            'world': {k: copy.deepcopy(v) for k, v in spec['world'].items()
                      if k in {'name', 'locations', 'connections', 'setting', 'deadline_hint'}},
            'public_canon': spec.get('public_canon', ''),
            'scene_goal': spec.get('goal', ''), 'step': state.get('step', 0),
            'co_present': public_people, 'known_facts': facts, 'available_items': items,
            'observed_events': event_text,
            'visible_event_records': [{k: copy.deepcopy(v) for k, v in e.items() if k in {'id', 'actor_id', 'action', 'dialogue', 'location', 'step', 'action_type'}} for e in visible],
            'director_instructions': [{'id': d['id'], 'text': d.get('text', d.get('instruction', ''))}
                                      for d in _active_directives(state, actor_id, int(state.get('step', 0)) + 1)]}


class AgentSandbox:
    def __init__(self, spec: dict, state: dict, generator: CandidateGenerator | None = None, llm=None):
        self.spec = normalize_spec(spec)
        self.state = copy.deepcopy(state)
        self.generator = generator
        self.llm = llm

    def propose(self, progress=None, cancel=None) -> list[dict]:
        progress = progress or (lambda *_args: None)
        cancel = cancel or (lambda: False)
        generator = self.generator or LLMCandidateGenerator(self.llm)
        events = []
        step = int(self.state.get('step', 0)) + 1
        for actor in self.spec['characters']:
            if cancel():
                raise RuntimeError('候选生成已取消')
            if self.state['actors'][actor['id']].get('status', 'active') != 'active':
                continue
            progress(actor['id'], 'deciding')
            context = role_context(self.spec, self.state, actor['id'])
            proposal = generator.propose(copy.deepcopy(context['actor']), copy.deepcopy(context), copy.deepcopy(context))
            if not isinstance(proposal, dict):
                raise ValueError('角色候选必须是 JSON 对象')
            event = copy.deepcopy(proposal)
            event['original_proposal'] = copy.deepcopy(proposal)
            # Providers commonly emit null for optional fields. Normalize that
            # representation only at the provider boundary; authored events stay
            # strictly validated, and an absent action never becomes fabricated.
            if isinstance(generator, LLMCandidateGenerator):
                for field in ('dialogue', 'inner_thought'):
                    if event.get(field) is None:
                        event[field] = ''
                for field in ('reveal_fact_ids', 'referenced_event_ids'):
                    if event.get(field) is None:
                        event[field] = []
            event.update(id=new_id('event'), step=step, actor_id=actor['id'],
                         source='llm' if isinstance(generator, LLMCandidateGenerator)
                         else getattr(generator, 'source', 'injected_generator'))
            event['action'] = event.get('action', event.get('public_action', ''))
            event['dialogue'] = event.get('dialogue', '')
            event['location'] = self.state['actors'][actor['id']]['location']
            event['move_to'] = event.get('move_to', event.get('goto_location', event['location']))
            event['checks'] = []
            events.append(event)
            progress(actor['id'], 'proposed')
            if cancel():
                raise RuntimeError('候选生成已取消')
        return project(self.spec, self.state, events)['events']


def project(spec: dict, state: dict, events: list[dict]) -> dict:
    """Arbitrate one candidate tick. Free text never changes objective facts."""
    spec = normalize_spec(spec)
    if not isinstance(events, list) or any(not isinstance(e, dict) for e in events):
        raise ValueError('候选事件必须是对象数组')
    proposed, events = copy.deepcopy(state), copy.deepcopy(events)
    actors = proposed['actors']
    locations = set(spec['world']['locations'])
    connections = spec['world'].get('connections', {})
    step = int(state.get('step', 0)) + 1
    seen_ids = {e['id'] for e in state.get('events', [])}
    moved = set()
    acting = set()
    for event in events:
        allowed = {'id', 'actor_id', 'step', 'action', 'public_action', 'dialogue', 'inner_thought',
                   'action_type', 'location', 'move_to', 'goto_location', 'target_id',
                   'transfer', 'pickup_item_id', 'drop_item_id', 'reveal_fact_ids',
                   'source', 'original_proposal', 'author_edits', 'referenced_event_ids'}
        for key in set(event) - allowed:
            event.pop(key)
        event['checks'] = []          # 先清空，后续字段级降级与检查都在此之后追加
        actor_id = event.get('actor_id')
        if not isinstance(actor_id, str) or actor_id not in actors:
            raise ValueError('候选事件引用不存在的角色')
        if actor_id in acting:
            raise ValueError('同一步中每个角色只能提出一个候选事件')
        acting.add(actor_id)
        if actors[actor_id].get('status', 'active') != 'active':
            raise ValueError('失去行动能力的角色不能行动')
        event.setdefault('id', new_id('event'))
        if not isinstance(event['id'], str) or not event['id']:
            raise ValueError('事件 id 必须是非空字符串')
        if event['id'] in seen_ids:
            raise ValueError('事件 ID 重复')
        seen_ids.add(event['id'])
        event['step'] = step
        event['action'] = event.get('action', event.get('public_action', ''))
        event['dialogue'] = event.get('dialogue', '')
        if not isinstance(event['action'], str) or not event['action'].strip():
            raise ValueError('候选事件必须包含非空动作文本')
        for field in ('dialogue', 'inner_thought', 'action_type', 'source'):
            if field in event and not isinstance(event[field], str):
                raise ValueError(f'{field} 必须是字符串')
        for field in ('move_to', 'goto_location', 'target_id', 'pickup_item_id', 'drop_item_id'):
            if event.get(field) is not None and not isinstance(event[field], str):
                raise ValueError(f'{field} 必须是字符串')
        if event.get('target_id') and event['target_id'] not in actors:
            # 模型可能虚构行动对象：忽略该字段并留下可见记录，不让整轮失败。
            event['checks'] = event.get('checks') or []
            event['checks'].append({'label': '行动目标', 'result': '角色不存在，已忽略该对象',
                                    'source': 'world.characters', 'proposed': event['target_id']})
            event['target_id'] = None
        for field in ('reveal_fact_ids', 'referenced_event_ids'):
            values = event.get(field, [])
            if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
                raise ValueError(f'{field} 必须是字符串数组')
        if event.get('transfer') is not None:
            value = event['transfer']
            if (not isinstance(value, dict) or set(value) != {'item_id', 'to_actor_id'}
                    or any(not isinstance(v, str) or not v for v in value.values())):
                # 结构不合法的转交：忽略并记录，不毁掉整轮
                event.setdefault('checks', []).append({'label': '道具转交', 'result': '字段不合法，已忽略该操作',
                                                       'source': 'transfer', 'proposed': str(value)[:60]})
                event['transfer'] = None
        destination = event.get('move_to', event.get('goto_location')) or actors[actor_id]['location']
        origin = state['actors'][actor_id]['location']
        if destination not in locations:
            # 不做隐性改写、也不毁掉整轮：留在原地，并留下可见的检查记录供作者判断。
            event['checks'].append({'label': '移动目标', 'result': '地点不在场景表中，已留在原地',
                                    'source': 'world.locations', 'proposed': destination})
            destination = origin
        if destination != origin:
            if actor_id in moved:
                raise ValueError('同一步中角色只能移动一次')
            if connections and destination not in connections.get(origin, []):
                event['checks'].append({'label': '移动目标', 'result': '与当前地点不连通，已留在原地',
                                        'source': 'world.connections', 'proposed': destination})
                destination = origin
        if destination != origin:
            actors[actor_id]['location'] = destination
            moved.add(actor_id)
            event['checks'].append({'label': '移动路径', 'result': '通过', 'source': 'world.connections'})
        event['location'] = destination
    entity_data = {key: {field: item.get(field) for field in ('state', 'holder', 'location')}
                   for key, item in proposed.get('items', {}).items()}
    for item in entity_data.values():
        item['state'] = item['state'] or 'active'
    machine = EntityStateMachine(entity_data)
    facts = _by_id(proposed.get('facts', []))
    all_checks = []
    for event in events:
        actor_id = event['actor_id']
        location = actors[actor_id]['location']
        witnesses = sorted(key for key, value in actors.items()
                           if value.get('location') == location and value.get('status', 'active') == 'active')
        event['observed_by'] = witnesses
        if event.get('target_id'):
            target = actors[event['target_id']]
            if target.get('location') != location:
                event['checks'].append({'label': '行动目标可见性', 'result': '未知', 'source': 'target_not_present'})
        transfer = event.get('transfer')
        if transfer:
            if not isinstance(transfer, dict):
                event['checks'].append({'label': '道具转交', 'result': '字段不是对象，已忽略该操作',
                                        'source': 'transfer', 'proposed': str(transfer)[:60]})
                event['transfer'] = None
                transfer = None
        if transfer:
            item_id, target = transfer.get('item_id'), transfer.get('to_actor_id')
            entity = machine.entities.get(item_id)
            original = state.get('items', {}).get(item_id, {})
            reason = None
            if (not entity or entity.state != 'active' or entity.holder != actor_id
                    or original.get('holder') != actor_id):
                reason = '角色当前并不持有该道具'
            elif target not in actors or actors[target]['location'] != location:
                reason = '接收者不在同一地点'
            if reason:
                event['checks'].append({'label': '道具转交', 'result': f'{reason}，已忽略该操作',
                                        'source': item_id, 'proposed': str(transfer)[:60]})
                event['transfer'] = None
            else:
                assessment = machine.assess(actor_id, location, item_id)
                machine.transfer(step, item_id, target)
                event['checks'].append({'label': '道具转交', 'result': '通过', 'source': item_id, 'assessment': assessment})
        for field, operation in [('pickup_item_id', 'pickup'), ('drop_item_id', 'drop')]:
            item_id = event.get(field)
            if not item_id:
                continue
            entity = machine.entities.get(item_id)
            note = None
            if not entity or entity.state != 'active':
                note = '道具不存在或已销毁'
            elif operation == 'pickup':
                original = state.get('items', {}).get(item_id, {})
                if (entity.holder is not None or entity.location != location
                        or original.get('holder') is not None or original.get('location') != location):
                    note = '该道具不在当前地点或并非无主'
            elif entity.holder != actor_id or state['items'][item_id].get('holder') != actor_id:
                note = '角色当前并不持有该道具'
            if note:
                # 模型提议了不合法的取用/放下：忽略该操作并留下可见依据，不让整轮失败。
                event['checks'].append({'label': '道具取用' if operation == 'pickup' else '道具放下',
                                        'result': f'{note}，已忽略该操作', 'source': item_id, 'proposed': item_id})
                event[field] = None
            else:
                if operation == 'pickup':
                    machine.pickup(step, item_id, actor_id)
                else:
                    machine.drop(step, item_id, location)
                event['checks'].append({'label': operation, 'result': '通过', 'source': item_id})
        for fact_id in event.get('reveal_fact_ids', []):
            fact = facts.get(fact_id)
            original = next((f for f in state.get('facts', []) if f['id'] == fact_id), None)
            if not fact or not original or actor_id not in original.get('known_by', []):
                # 角色不能披露自己不知道的事：忽略该条并记录，不让整轮失败。
                event['checks'].append({'label': '信息披露', 'result': '角色尚不知道该事实，已忽略',
                                        'source': fact_id})
                continue
            if fact_id in state.get('locked_fact_ids', []):
                event['checks'].append({'label': '信息披露', 'result': '事实已锁定，已忽略该披露',
                                        'source': fact_id})
                continue
            fact['known_by'] = sorted(set(fact.get('known_by', [])) | set(witnesses))
            fact.setdefault('observations', []).append({'event_id': event['id'], 'actor_ids': witnesses, 'kind': 'disclosure'})
            event['checks'].append({'label': '信息披露', 'result': '通过', 'source': fact_id})
        for witness in witnesses:
            actors[witness].setdefault('observation_ids', []).append(event['id'])
        all_checks.extend(event['checks'])
    for item_id, entity in machine.entities.items():
        proposed['items'][item_id].update(state=entity.state, holder=entity.holder, location=entity.location)
    proposed['facts'] = list(facts.values())
    proposed['events'] = proposed.get('events', []) + events
    proposed['step'] = step if events else state.get('step', 0)
    proposed['event_counter'] = int(state.get('event_counter', len(state.get('events', [])))) + len(events)
    acting_ids = {e['actor_id'] for e in events}
    applied_ids = {d['id'] for actor_id in acting_ids for d in _active_directives(state, actor_id, step)}
    for directive in proposed.get('directives', []) if events else []:
        if directive.get('status', 'pending') != 'pending':
            continue
        if directive['id'] in applied_ids:
            directive.update(status='applied', applied_step=step)
        elif directive.get('end_step') is not None and int(directive['end_step']) < step:
            directive['status'] = 'expired'
    state_diff = {key: {'before': copy.deepcopy(state.get(key)), 'after': copy.deepcopy(proposed.get(key))}
                  for key in ('actors', 'items', 'facts', 'step', 'event_counter', 'directives')
                  if state.get(key) != proposed.get(key)}
    return {'state': proposed, 'events': events, 'checks': all_checks, 'state_diff': state_diff}
