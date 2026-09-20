"""Deterministic role policy for local demonstrations, not an LLM simulator.
Every decision consumes only a role_context; templates interpolate actual state.
"""
from __future__ import annotations

class OfflineGenerator:
    source = 'offline_rule_v1'

    def propose(self, actor, context, state):
        aid, name = actor['id'], actor['name']
        step = int(context['step']) + 1
        location = actor['location']
        people = context['co_present']
        past = context.get('visible_event_records', [])
        other = next((e for e in reversed(past) if e['actor_id'] != aid), None)
        target = people[(step - 1) % len(people)] if people else None
        own_items = [i for i in context['available_items'] if i.get('holder') == aid]
        loose = [i for i in context['available_items'] if not i.get('holder') and i.get('state') != 'destroyed']
        facts = context['known_facts']
        places = context['world']['locations']
        connections = context['world'].get('connections', {})
        neighbors = connections.get(location, []) if connections else [p for p in places if p != location]
        goal = actor.get('goal') or actor.get('hidden_goal') or '了解现场情况'
        result = {'action': '', 'dialogue': '', 'action_type': '观察', 'move_to': location,
                  'referenced_event_ids': [other['id']] if other else []}
        mode = (step - 1) % 4
        # First establish contact; later cycles alternate concrete, visible interactions.
        if not people and neighbors:
            result.update(action=f'{name}离开{location}，前往{neighbors[0]}寻找交流机会',
                          action_type='移动', move_to=neighbors[0])
        elif mode == 1 and own_items and target:
            item = own_items[0]
            result.update(action=f'{name}将{item["name"]}交给{target["name"]}核对',
                          dialogue=f'请看这份{item["name"]}，这关系到{goal}。', action_type='交付',
                          target_id=target['id'], transfer={'item_id': item['id'], 'to_actor_id': target['id']})
        elif mode == 2 and facts and target:
            fact = facts[(step // 4) % len(facts)]
            result.update(action=f'{name}面向在场角色说明已知情况', dialogue=f'我知道的是：{fact["label"]}。',
                          action_type='披露', target_id=target['id'], reveal_fact_ids=[fact['id']])
        elif mode == 3 and neighbors:
            place = neighbors[(sum(ord(c) for c in aid) + step) % len(neighbors)]
            result.update(action=f'{name}走向{place}，准备从另一个位置观察局面', action_type='移动', move_to=place)
        elif loose:
            item = loose[0]
            result.update(action=f'{name}拿起面前的{item["name"]}查看', action_type='取用', pickup_item_id=item['id'])
        elif other:
            topic = other.get('dialogue') or other['action']
            result.update(action=f'{name}转向刚才发言的方向，回应自己观察到的情况',
                          dialogue=f'关于“{topic[:50]}”，我还需要确认。这关系到{goal}。',
                          action_type='回应', target_id=target['id'] if target else None)
        else:
            result.update(action=f'{name}环顾{location}，向在场者说明自己的打算',
                          dialogue=f'我希望{goal}。我们先把各自知道的情况说清楚。',
                          action_type='交流', target_id=target['id'] if target else None)
        instructions = context.get('director_instructions', [])
        if instructions:
            result['action'] += '；执行导演提示：' + '；'.join(d['text'] for d in instructions)
        return result
