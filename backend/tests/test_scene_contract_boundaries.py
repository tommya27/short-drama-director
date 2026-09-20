from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from importlib import import_module
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event

import pytest
from fastapi.testclient import TestClient

from backend.director_core.engine import DirectorStore
from backend.director_core.offline import OfflineGenerator
from backend.director_core.scene_input import expand


@pytest.fixture
def api(monkeypatch):
    with TemporaryDirectory() as directory:
        store = DirectorStore(Path(directory) / 'director.db')
        main = import_module('backend.main')
        monkeypatch.setattr(main, 'store', store)
        with TestClient(main.app) as client:
            yield client, store


def create_scene(client):
    spec = expand('古宅里的秘密使三个人改变计划')['scene_spec']
    result = client.post('/api/v1/scenes', json=spec)
    assert result.status_code == 200
    return result.json()


def test_full_frontend_scene_spec_roundtrip_preserves_zones_and_goals(api):
    client, store = api
    scene = create_scene(client)
    sid = scene['scene_id']
    spec = deepcopy(scene['spec'])
    assert spec['scene_manifest']['scene_key'] == 'mansion'
    assert spec['locations'] == spec['world']['locations']
    # The frontend deliberately normalizes away world and characters.
    spec.pop('world')
    spec.pop('characters')
    spec['goals'] = ['找回钥匙', '守住秘密']
    spec['locations'].append('古宅·后院')
    spec['title'] = '另一种选择'
    response = client.patch(f'/api/v1/scenes/{sid}', json={**spec, 'base_revision': 0})
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved['spec']['scene_id'] == sid
    assert saved['spec']['locations'] == spec['locations']
    assert saved['state']['locations'] == spec['locations']
    assert saved['spec']['world']['locations'] == spec['locations']
    assert saved['spec']['goals'] == spec['goals']
    assert saved['state']['revision'] == 1
    reloaded = DirectorStore(store.repo.path).scene_view(sid)
    assert reloaded['spec']['locations'] == spec['locations']
    assert reloaded['spec']['goals'] == spec['goals']


def test_scene_id_change_is_rejected_without_mutation(api):
    client, store = api
    scene = create_scene(client)
    sid = scene['scene_id']
    response = client.patch(f'/api/v1/scenes/{sid}', json={'scene_id': 'other', 'title': '不应保存'})
    assert response.status_code == 422
    assert store.scene_view(sid) == scene


@pytest.mark.parametrize('patch,status', [
    ({'title': '不得覆盖', 'base_revision': 99}, 409),
    ({'title': '不得覆盖', 'goals': '不是数组'}, 422),
    ({'title': '不得覆盖', 'locations': ['不存在的地点']}, 422),
    ({'base_revision': 99}, 409),
])
def test_branch_activation_and_scene_changes_are_atomic(api, patch, status):
    client, store = api
    scene = create_scene(client)
    sid = scene['scene_id']
    branch = store.create_branch(sid, {'name': '分支', 'activate': False})
    before = store.scene_view(sid)
    before_branch = store.repo.get_branch(store.owner, sid, branch['branch_id'])
    response = client.patch(f'/api/v1/scenes/{sid}', json={**patch, 'active_branch_id': branch['branch_id']})
    assert response.status_code == status, response.text
    assert store.scene_view(sid) == before
    assert store.repo.get_branch(store.owner, sid, branch['branch_id']) == before_branch


def test_successful_scene_edit_and_activation_are_persisted_together(api):
    client, store = api
    sid = create_scene(client)['scene_id']
    branch = store.create_branch(sid, {'name': '分支', 'activate': False})
    response = client.patch(f'/api/v1/scenes/{sid}', json={
        'scene_id': sid, 'active_branch_id': branch['branch_id'],
        'title': '分支标题', 'goals': ['查明真相'], 'base_revision': 0,
    })
    assert response.status_code == 200, response.text
    reloaded = DirectorStore(store.repo.path).scene_view(sid)
    assert reloaded['active_branch_id'] == branch['branch_id']
    assert reloaded['spec']['title'] == '分支标题'
    assert reloaded['state']['revision'] == 1
    assert store.repo.get_branch(store.owner, sid, 'main')['revision'] == 0


def test_cancellation_discards_a_late_generation_result(api):
    client, store = api
    sid = create_scene(client)['scene_id']
    started, finish = Event(), Event()

    class DelayedOfflineGenerator(OfflineGenerator):
        def propose(self, actor, context, state):
            started.set()
            assert finish.wait(timeout=10), 'test did not release the offline generator'
            return super().propose(actor, context, state)

    store.service.generator_factory = DelayedOfflineGenerator
    before = store.current_state(sid)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(client.post, f'/api/v1/scenes/{sid}/drafts',
                              json={'base_revision': 0, 'request_id': 'cancel-during-generation'})
        try:
            assert started.wait(timeout=10), 'generation did not start'
            cancelled = client.post('/api/v1/requests/cancel-during-generation/cancel')
            assert cancelled.status_code == 200
        finally:
            finish.set()
        response = pending.result(timeout=10)
    assert response.status_code == 409, response.text
    drafts = store.repo.list_drafts(store.owner, sid, 'main')
    assert len(drafts) == 1
    assert drafts[0]['status'] == 'discarded'
    assert drafts[0]['preview'] is None
    assert store.current_state(sid) == before
    retry = client.post(f'/api/v1/scenes/{sid}/drafts', json={'request_id': 'cancel-during-generation'})
    assert retry.status_code == 409
    assert len(store.repo.list_drafts(store.owner, sid, 'main')) == 1
    assert client.post(f'/api/v1/drafts/{drafts[0]["id"]}/commit').status_code == 409


@pytest.mark.parametrize('payload', [
    {'title': 123}, {'actors': None}, {'actors': '演员'}, {'actors': ['甲']},
    {'items': None}, {'facts': '秘密'}, {'goals': '查明真相'},
    {'actors': [{'id': 'a'}, {'id': 'a'}]},
    {'actors': [{'id': 'a'}], 'facts': [{'id': 'f', 'label': '秘密', 'known_by': ['missing']}]},
    {'locations': []}, {'world': None},
])
def test_invalid_scene_inputs_return_422(api, payload):
    client, store = api
    assert store.repo.list_scenes(store.owner) == []
    result = client.post('/api/v1/scenes', json=payload)
    assert result.status_code == 422, result.text
    assert store.repo.list_scenes(store.owner) == []


@pytest.mark.parametrize('payload', [{'base_revision': True}, {'request_id': []}, {'candidate_events': 'invalid'}])
def test_invalid_draft_inputs_return_422_and_do_not_change_story(api, payload):
    client, store = api
    sid = create_scene(client)['scene_id']
    before = store.current_state(sid)
    result = client.post(f'/api/v1/scenes/{sid}/drafts', json=payload)
    assert result.status_code == 422, result.text
    assert store.current_state(sid) == before
    assert store.repo.list_drafts(store.owner, sid, 'main') == []
