from copy import deepcopy
import pytest
from fastapi.testclient import TestClient
from backend import main
from backend.director_core.engine import DirectorStore, ConflictError


def commit(store, sid, branch='main', events=None):
    revision = store.current_state(sid, branch)['revision']
    payload = {'branch_id': branch, 'base_revision': revision}
    if events is not None:
        payload['candidate_events'] = events
    draft = store.create_draft(sid, payload)
    store.preview_draft(draft['draft_id'], draft['version'])
    store.commit_draft(draft['draft_id'], revision, draft['draft_id'], draft['version'])


def test_replay_preserves_historical_world_and_never_writes(tmp_path):
    store = DirectorStore(tmp_path / 'history.db')
    sid = store.create_scene({'title': '原场景', 'location': '大厅', 'locations': ['大厅', '门口'],
        'actors': [{'id': 'a', 'name': '甲', 'location': '大厅'}, {'id': 'b', 'name': '乙', 'location': '大厅'}],
        'facts': [{'id': 'secret', 'label': '授权无效', 'known_by': ['a']}],
        'items': [{'id': 'doc', 'name': '文件', 'holder': 'a'}]})['scene_id']
    before = deepcopy(store.current_state(sid))
    commit(store, sid, events=[{'actor_id': 'a', 'action': '交付证据', 'transfer': {'item_id': 'doc', 'to_actor_id': 'b'}, 'reveal_fact_ids': ['secret']}])
    commit(store, sid, events=[{'actor_id': 'b', 'action': '走向门口', 'move_to': '门口'}])
    store.update_scene(sid, {'base_revision': 2, 'title': '新场景'})
    latest = deepcopy(store.current_state(sid))
    history = store.replay(sid, 'main', 3)
    assert history['frames'][0]['state'] == before
    assert history['frames'][0]['scene_spec']['title'] == '原场景'
    assert history['frames'][0]['state']['items']['doc']['holder'] == 'a'
    assert history['frames'][0]['state']['facts'][0]['known_by'] == ['a']
    assert history['frames'][1]['state']['items']['doc']['holder'] == 'b'
    assert history['frames'][1]['state']['actors']['b']['location'] == '大厅'
    assert history['frames'][2]['state']['actors']['b']['location'] == '门口'
    assert history['frames'][-1]['scene_spec']['title'] == '新场景'
    assert store.current_state(sid) == latest
    history['frames'][0]['state']['actors']['a']['location'] = 'fake'
    assert store.replay(sid)['frames'][0]['state'] == before
    with pytest.raises(ConflictError):
        store.replay(sid, 'main', 0)


def test_replay_excludes_future_parent_edits_and_pending_drafts(tmp_path):
    store = DirectorStore(tmp_path / 'fork.db')
    sid = store.create_scene({'title': '共同开场'})['scene_id']
    commit(store, sid)
    child = store.create_branch(sid, {'name': '子分支'})['branch_id']
    store.update_scene(sid, {'branch_id': 'main', 'base_revision': 1, 'title': '父线后来改名'})
    commit(store, sid, child)
    store.create_draft(sid, {'branch_id': child})
    history = store.replay(sid, child)
    assert [f['revision'] for f in history['frames']] == [0, 1, 2]
    assert all(f['scene_spec']['title'] == '共同开场' for f in history['frames'])
    assert all(f['state']['branch_id'] == child for f in history['frames'])
    assert history['frames'][-1]['state'] == store.current_state(sid, child)
    with pytest.raises(LookupError):
        store.repo.replay_checkpoints('another-owner', sid, child)


def test_replay_api_validation_and_read_only(tmp_path, monkeypatch):
    store = DirectorStore(tmp_path / 'api.db')
    monkeypatch.setattr(main, 'store', store)
    sid = store.create_scene({'title': '回看'})['scene_id']
    client = TestClient(main.app)
    url = f'/api/v1/scenes/{sid}/replay'
    assert client.get(url).json()['frames'][0]['revision'] == 0
    assert client.get(url + '?expected_revision=9').status_code == 409
    assert client.get(url + '?expected_revision=-1').status_code == 422
    assert client.get(url + '?branch_id=missing').status_code == 404
    assert store.current_state(sid)['revision'] == 0
