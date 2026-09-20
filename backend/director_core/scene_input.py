"""Versioned, local-only scene creation helpers."""
from copy import deepcopy
from .models import normalize_spec, default_boardroom_spec

def portable_spec(payload):
    if not isinstance(payload, dict):
        raise ValueError('场景必须是对象')
    data = deepcopy(payload)
    if 'actors' in data:
        data['characters'] = data.pop('actors')
    if 'characters' in data and (not isinstance(data['characters'],list) or
            any(not isinstance(actor,dict) for actor in data['characters'])):
        raise ValueError('actors 必须是角色对象数组')
    for field in ('items','facts','goals'):
        if field in data and not isinstance(data[field],list):
            raise ValueError(f'{field} 必须是数组')
    if 'location' not in data and data.get('characters'):
        data['location'] = data['characters'][0].get('location') or '现场'
    if 'characters' not in data:
        data.update({k: v for k,v in default_boardroom_spec().to_dict().items() if k not in data})
        data['characters'] = data['characters'][:3]
        ids = {a['id'] for a in data['characters']}
        for f in data.get('facts', []):
            f['known_by'] = [a for a in f.get('known_by', []) if a in ids]
    if 'sceneManifest' in data:
        data['scene_manifest'] = {'scene_key': data.pop('sceneManifest')}
    data.setdefault('scene_manifest', {'scene_key': 'generic'})
    data.setdefault('author_facts', data.pop('authorFacts', []))
    if not isinstance(data['author_facts'], list) or any(not isinstance(x, (str, dict)) for x in data['author_facts']):
        raise ValueError('author_facts 必须是事实数组')
    for idx, raw in enumerate(data.get('items', [])):
        if isinstance(raw, str):
            data['items'][idx] = {'id': f'item_{idx+1}', 'name': raw, 'location': data.get('location', '现场')}
    if 'world' not in data:
        location = data.get('location', '现场')
        places = data.get('locations', list(dict.fromkeys(
            [location] + [actor.get('location',location) for actor in data.get('characters',[])])))
        if not isinstance(places,list) or not all(isinstance(x,str) for x in places):
            raise ValueError('locations 必须是字符串数组')
        data['world'] = {'locations': places, 'connections': {}, 'name': location, 'setting': data.get('conflict', '')}
    result = normalize_spec(data)
    for f in result.get('facts', []):
        if not isinstance(f.get('label'), str) or not f['label'].strip():
            raise ValueError('事实 label 不能为空')
    if not isinstance(result.get('scene_manifest'), dict):
        raise ValueError('scene_manifest 必须是对象')
    return result


def expand(premise):
    if not premise.strip(): raise ValueError('想法不能为空')
    if any(w in premise for w in ['董事','公司','专利','授权']):
        spec = default_boardroom_spec().to_dict()
        spec['characters'] = spec['characters'][:3]
        spec['facts'] = spec['facts'][:3]
        spec['scene_manifest'] = {'scene_key':'boardroom'}
    else:
        location = next((x for x in ['客栈','古宅','办公室','校园','医院','咖啡馆'] if x in premise), '故事现场')
        spec = {'location':location,'characters':[
            {'id':'lead','name':'主角','role':'提出想法的人','goal':'查明冲突的原因','location':location},
            {'id':'opponent','name':'对手','role':'持不同立场的人','goal':'守住自己的利益','location':location},
            {'id':'witness','name':'见证者','role':'知情人','goal':'判断何时公开线索','location':location}],
            'items':[{'id':'clue','name':'关键线索','holder':'witness'}],
            'facts':[{'id':'clue_known','label':'线索的来源尚未公开','known_by':['witness'],'source':'创作建议'}],
            'scene_manifest':{'scene_key': {'客栈':'inn','古宅':'mansion','办公室':'office'}.get(location,'generic')}}
    spec.update(title=premise[:30], premise=premise, conflict=premise,
                goal='让角色在一场戏中作出影响冲突的选择')
    location = spec['location']
    places=[location,location+'·入口',location+'·一侧']
    spec['world']={'name':location,'locations':places,'connections':{},'setting':premise}
    spec=portable_spec(spec)
    return {'premise':premise,'questions':['谁最想得到什么？','谁知道别人不知道的信息？','哪一个道具会改变选择？'],
            'scene_spec':public_spec(spec)}


def public_spec(spec):
    result = deepcopy(spec)
    result['actors'] = deepcopy(spec['characters'])
    result['locations'] = deepcopy(spec['world']['locations'])
    return result
