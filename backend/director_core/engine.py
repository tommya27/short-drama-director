"""SQLite-backed facade for the standalone director API.
The narrative service/repository were ported into this package; this facade keeps
HTTP response names stable while all state is persisted in SQLite.
"""
from __future__ import annotations
from copy import deepcopy
from threading import RLock
from typing import Any
from .models import normalize_spec, default_boardroom_spec, default_state, new_id, now_iso
from .repository import NarrativeRepository, ConflictError
from .service import NarrativeService
from .offline import OfflineGenerator
from .scene_input import portable_spec
from .sandbox import project, role_context
from .dramatic import ensure_dramatic, polish_screenplay, render_screenplay, render_storyboard

class NotFoundError(LookupError): pass

class DirectorStore:
    def __init__(self, db_path=None, generator_factory=None):
        self.repo = NarrativeRepository(db_path)
        self.service = NarrativeService(self.repo, generator_factory=generator_factory or (lambda: OfflineGenerator()))
        self._lock = RLock()
        self.owner = 'local'
        self.outputs: dict[str, dict[str, Any]] = {}
        self.cancelled: set[str] = set()
        with self.repo._connection(write=True) as c:
            c.execute('CREATE TABLE IF NOT EXISTS director_outputs (id TEXT PRIMARY KEY, scene_id TEXT NOT NULL, payload_json TEXT NOT NULL)')
            c.execute('CREATE TABLE IF NOT EXISTS director_requests (id TEXT PRIMARY KEY, cancelled INTEGER NOT NULL DEFAULT 0)')

    def scene_view(self, sid, branch_id=None): return self._scene_view(sid, branch_id)
    def draft_view(self, draft): return deepcopy(draft)

    def _bid(self,sid,bid=None):
        if bid == 'root': return 'main'
        if bid: return bid
        scene=self.repo.get_scene(self.owner,sid)
        if scene is None: raise NotFoundError('场景不存在')
        return scene['active_branch']

    def _activate(self,sid,bid):
        self.repo.activate_branch(self.owner,sid,bid)

    @staticmethod
    def _version(value,default):
        if value is None: return default
        if isinstance(value,bool) or not isinstance(value,int) or value < 0:
            raise ValueError('版本号必须是非负整数')
        return value

    def _state_view(self,branch):
        state=deepcopy(branch['state']); state['branch_id']=branch['id']
        state['locations']=deepcopy(branch['spec']['world']['locations'])
        state['item_ownership']={k:v.get('holder') or v.get('location') for k,v in state.get('items',{}).items()}
        state['observations']={aid:deepcopy(a.get('observation_ids',[])) for aid,a in state['actors'].items()}
        cards={a['id']:a for a in branch['spec']['characters']}
        for aid, actor in state['actors'].items():
            actor.update(id=aid,name=cards[aid]['name'],role=cards[aid].get('role','角色'),goal=cards[aid].get('goal',''))
        for event in state['events']:
            event['committed_change']=True
        return state

    def _branch(self, sid, bid='main'):
        result=self.repo.get_branch(self.owner,sid,bid)
        if result is None: raise NotFoundError('场景或分支不存在')
        return result

    def _scene_view(self,sid,active=None):
        scene=self.repo.get_scene(self.owner,sid)
        if scene is None: raise NotFoundError('场景不存在')
        bid=active or scene.get('active_branch') or 'main'
        branch=self._branch(sid,bid)
        branches=[]
        for b in scene.get('branches',[]):
            branches.append({k:deepcopy(b[k]) for k in ('id','name','parent_branch','revision','spec_revision','created_at','updated_at')})
            branches[-1]['branch_id']=branches[-1].pop('id')
            branches[-1]['parent_branch_id']=branches[-1].pop('parent_branch')
        spec=deepcopy(branch['spec']); spec['scene_id']=sid; spec['actors']=deepcopy(spec.get('characters',[]))
        # 读取路径不调模型：老场景缺 contract/beats 时用内置模板补齐（并如实标注 template），
        # 这样界面上的"剧情分段"和事件归属永远有据可依。
        if not spec.get('beats') or not spec.get('contract'):
            spec=ensure_dramatic(spec, use_model=False)
        spec['locations']=deepcopy(spec['world']['locations'])
        spec.setdefault('goals',[])
        return {'scene_id':sid,'scene_spec':spec,'spec':spec,**{k:deepcopy(v) for k,v in spec.items() if k not in ('scene_id',)},
                'active_branch_id':bid,'branches':branches,'state':self._state_view(branch),
                'created_at':scene['created_at'],'updated_at':scene['updated_at']}

    def create_scene(self,payload):
        spec=portable_spec(payload)
        result=self.service.create_scene(self.owner,spec)
        return self._scene_view(result['id'] if 'id' in result else result['scene_id'])

    def get_scene(self,sid): return self._scene_view(sid)
    def update_scene(self,sid,patch):
        scene=self.repo.get_scene(self.owner,sid)
        if scene is None: raise NotFoundError('场景不存在')
        patch=deepcopy(patch)
        if 'scene_id' in patch and patch.pop('scene_id') != sid:
            raise ValueError('不能修改场景 scene_id')
        active=patch.pop('active_branch_id',None)
        requested_branch=patch.pop('branch_id',None)
        if active is not None and (not isinstance(active,str) or not active):
            raise ValueError('active_branch_id 必须是非空字符串')
        if requested_branch is not None and (not isinstance(requested_branch,str) or not requested_branch):
            raise ValueError('branch_id 必须是非空字符串')
        if active and requested_branch and self._bid(sid,active) != self._bid(sid,requested_branch):
            raise ValueError('active_branch_id 与 branch_id 必须一致')
        bid=self._bid(sid,requested_branch or active)
        branch=self._branch(sid,bid)
        expected=self._version(patch.pop('base_revision',None),branch['revision'])
        allowed={'characters','actors','items','facts','title','goal','goals','conflict','location','locations','genre','scene_manifest','author_facts','relationships','world','premise'}
        # contract / beats / dramatic_source 由剧情结构层在服务端维护（只读）；
        # 前端整份回写场景时会带上它们，这里忽略而不报错。
        for readonly in ('contract','beats','dramatic_source'):
            patch.pop(readonly,None)
        if set(patch)-allowed: raise ValueError('不支持的场景修改字段：'+','.join(sorted(set(patch)-allowed)))
        changes=patch
        if 'goals' in changes and (not isinstance(changes['goals'],list) or any(not isinstance(v,str) for v in changes['goals'])):
            raise ValueError('goals 必须是字符串数组')
        if 'world' in changes and not isinstance(changes['world'],dict):
            raise ValueError('world 必须是对象')
        if 'locations' in changes:
            locations=changes.pop('locations')
            if not isinstance(locations,list) or not locations or any(not isinstance(v,str) or not v.strip() for v in locations):
                raise ValueError('locations 必须是非空地点字符串数组')
            world={**deepcopy(branch['spec']['world']),**changes.get('world',{})}
            world['locations']=deepcopy(locations)
            changes['world']=world
        if 'actors' in changes: changes['characters']=changes.pop('actors')
        if 'scene_manifest' in changes and isinstance(changes['scene_manifest'],str): changes['scene_manifest']={'scene_key':changes['scene_manifest']}
        if changes:
            # Spec, world checkpoint and active branch are written in one SQLite transaction.
            self.service.edit_scene(self.owner,sid,bid,expected,changes,activate=active is not None)
        elif active is not None:
            self.repo.activate_branch(self.owner,sid,bid,base_revision=expected)
        elif expected != branch['revision']:
            raise ConflictError('正式版本已变化，请刷新后重试')
        return self._scene_view(sid,bid)
    def current_state(self,sid,bid=None): return self._state_view(self._branch(sid,self._bid(sid,bid)))
    def replay(self,sid,bid=None,expected_revision=None):
        bid=self._bid(sid,bid)
        revision, checkpoints=self.repo.replay_checkpoints(self.owner,sid,bid,expected_revision)
        frames=[]
        for checkpoint in checkpoints:
            spec=deepcopy(checkpoint['spec'])
            spec.update(scene_id=sid,actors=deepcopy(spec['characters']),locations=deepcopy(spec['world']['locations']))
            frames.append({'frame_id':f"{checkpoint['branch_id']}:{checkpoint['revision']}",
                'source_branch_id':checkpoint['branch_id'],'revision':checkpoint['revision'],
                'reason':checkpoint['reason'],'scene_spec':spec,
                'state':self._state_view({'id':bid,'spec':checkpoint['spec'],'state':checkpoint['state']})})
        return {'scene_id':sid,'branch_id':bid,'revision':revision,'frames':frames}
    def context(self,sid,actor_id,bid=None):
        branch=self._branch(sid,self._bid(sid,bid))
        if actor_id not in branch['state']['actors']:raise ValueError('角色不存在')
        return role_context(branch['spec'],branch['state'],actor_id)
    def visible_events(self,sid,actor_id=None,bid=None):
        state=self.current_state(sid,bid)
        if not actor_id:return deepcopy(state.get('events',[]))
        if actor_id not in state['actors']:raise ValueError('角色不存在')
        safe={'id','step','actor_id','action','dialogue','location','target_id','action_type','committed_change','observed_by'}
        return [{k:deepcopy(v) for k,v in e.items() if k in safe} for e in state.get('events',[]) if actor_id in e.get('observed_by',[]) or actor_id==e.get('actor_id')]
    def visible_facts(self,sid,actor_id=None,bid=None):
        state=self.current_state(sid,bid)
        if actor_id and actor_id not in state['actors']:raise ValueError('角色不存在')
        return deepcopy([f for f in state.get('facts',[]) if not actor_id or actor_id in f.get('known_by',[])])
    def create_draft(self,sid,payload):
        bid=self._bid(sid,payload.get('branch_id')); branch=self._branch(sid,bid)
        base=self._version(payload.get('base_revision'),branch['revision'])
        if int(base)!=branch['revision']: raise ConflictError('正式版本已变化，请刷新场景')
        request_id=payload.get('request_id')
        if request_id is not None and (not isinstance(request_id,str) or not request_id.strip()):raise ValueError('request_id 必须是非空字符串')
        if request_id:
            with self.repo._connection(write=True) as c:
                c.execute('INSERT OR IGNORE INTO director_requests VALUES (?,0)',(request_id,))
        if request_id and self.is_cancelled(request_id):raise ConflictError('请求已取消')
        if 'candidate_events' in payload:
            projected=project(branch['spec'],branch['state'],payload['candidate_events'])
            draft=self.repo.create_draft(self.owner,sid,bid,base,{'events':projected['events'],'locks':payload.get('locks',[])})
        else:
            draft=self.service.generate_draft(self.owner,sid,bid,base_revision=base,
                regenerate_from=payload.get('regenerate_from'),regenerate_version=payload.get('regenerate_version'))
        if request_id and self.is_cancelled(request_id):
            self.repo.discard_draft(self.owner,draft['id'],expected_version=draft['version'])
            raise ConflictError('请求已取消，迟到结果已丢弃')
        return self._draft_view(draft)
    def is_cancelled(self,request_id):
        with self.repo._connection() as c:
            row=c.execute('SELECT cancelled FROM director_requests WHERE id=?',(request_id,)).fetchone()
            return row is not None and bool(row[0])
    def cancel_request(self,request_id):
        with self.repo._connection(write=True) as c:
            c.execute('INSERT INTO director_requests VALUES (?,1) ON CONFLICT(id) DO UPDATE SET cancelled=1',(request_id,))
        return {'request_id':request_id,'status':'cancelled'}
    def _draft_view(self,d):
        result=deepcopy(d)
        result.update({'draft_id':d['id'],'base_revision':d['base_revision'],'candidate_events':deepcopy(d['payload'].get('events',[])),
                       'locks':deepcopy(d['payload'].get('locks',[])),'generation_source':d['payload'].get('source'),'assessment':deepcopy(d['payload'].get('assessment')),'validation':{'valid':True,'errors':[]},
                       'status':('previewed' if d.get('preview') else 'pending') if d['status']=='awaiting_approval' else d['status'],'version':d['version']})
        result.update(proposed_state=None,preview_state=None,state_diff={})
        if d.get('preview') is not None:
            result['proposed_state']=deepcopy(d['preview'].get('state')); result['preview']=deepcopy(d['preview'])
            branch=self._branch(d['scene_id'],d['branch_id']); branch['state']=d['preview']['state']
            result['proposed_state']=self._state_view(branch)
            result['preview_state']=deepcopy(result['proposed_state']); result['state_diff']=deepcopy(d['preview'].get('state_diff',{}))
            for event in result['proposed_state']['events']:
                event['committed_change']=event['id'] not in {e['id'] for e in result['candidate_events']}
        result.pop('id',None); result.pop('payload',None); result.pop('original_payload',None)
        return result
    def get_draft(self,did):
        d=self.repo.get_draft(self.owner,did)
        if d is None: raise NotFoundError('草稿不存在')
        return self._draft_view(d)
    def patch_draft(self,did,payload):
        d=self.repo.get_draft(self.owner,did)
        if d is None: raise NotFoundError('草稿不存在')
        events=payload.get('candidate_events',payload.get('events'))
        changes={}
        if events is not None: changes['events']=events
        if 'locks' in payload: changes['locks']=payload['locks']
        out=self.service.edit_draft(self.owner,did,events if events is not None else d['payload'].get('events',[]),payload.get('locks',d['locks']),expected_version=self._version(payload.get('expected_version',payload.get('version')),d['version']),unlock_paths=payload.get('unlock_paths',[])) if changes else d
        return self._draft_view(out)
    def preview_draft(self,did,expected_version=None):
        d=self.repo.get_draft(self.owner,did)
        if d is None: raise NotFoundError('草稿不存在')
        result=self.service.preview(self.owner,did,expected_version=self._version(expected_version,d['version']))
        return self._draft_view(result)
    def commit_draft(self,did,expected_revision=None,idempotency_key=None,expected_version=None):
        d=self.repo.get_draft(self.owner,did)
        if d is None: raise NotFoundError('草稿不存在')
        if idempotency_key is None: idempotency_key='commit:'+did
        if expected_revision is not None and int(expected_revision)!=d['base_revision']: raise ConflictError('提交版本冲突')
        result=self.service.commit(self.owner,did,idempotency_key,expected_version=self._version(expected_version,d['version']))
        return {**result,'status':'committed','committed_revision':result['revision']}
    def discard_draft(self,did,expected_version=None):
        d=self.repo.get_draft(self.owner,did)
        if d is None: raise NotFoundError('草稿不存在')
        return self._draft_view(self.repo.discard_draft(self.owner,did,expected_version=self._version(expected_version,d['version'])))
    def create_branch(self,sid,payload):
        source=self._bid(sid,payload.get('from_branch_id') or payload.get('branch_id'))
        if source == 'root': source = 'main'
        branch=self.repo.create_branch(self.owner,sid,source,str(payload.get('name') or '试演分支'),base_revision=payload.get('base_revision'))
        view={k:deepcopy(branch[k]) for k in ('id','name','parent_branch','revision','spec_revision','created_at','updated_at')}
        view['branch_id']=view.pop('id'); view['parent_branch_id']=view.pop('parent_branch'); view['state']=self._state_view(branch)
        if payload.get('activate',True):self._activate(sid,view['branch_id'])
        return view
    def add_directive(self,sid,payload):
        bid=self._bid(sid,payload.get('branch_id')); branch=self._branch(sid,bid)
        start=int(payload.get('start_step',branch['state'].get('step',0)+1)); end=payload.get('end_step')
        result=self.service.directive(self.owner,sid,bid,branch['revision'],text=str(payload.get('text') or payload.get('instruction') or ''),target_actor_id=payload.get('target_actor_id'),start_step=start,end_step=int(end if end is not None else start))
        return result['directive']
    def remove_directive(self,sid,did,bid=None):
        bid=self._bid(sid,bid); branch=self._branch(sid,bid); return self.service.cancel_directive(self.owner,sid,bid,branch['revision'],did)
    def advance_beat(self,sid,payload):
        bid=self._bid(sid,payload.get('branch_id')); branch=self._branch(sid,bid)
        base=self._version(payload.get('base_revision'),branch['revision'])
        return self.service.advance_beat(self.owner,sid,bid,base_revision=base)

    def create_output(self,sid,payload):
        bid=self._bid(sid,payload.get('branch_id')); branch=self._branch(sid,bid); ids=payload.get('source_event_ids') or payload.get('event_ids') or [e['id'] for e in branch['state'].get('events',[])]
        kind=str(payload.get('type') or 'script')
        # 剧本/分镜默认用确定性渲染器：格式稳定、可复现、每段都能指回来源事件（不调模型）
        if payload.get('deterministic', True) and kind in {'script','screenplay','storyboard'}:
            committed=branch['state'].get('events',[])
            chosen=[e for e in committed if e.get('id') in set(ids)] or list(committed)
            if not chosen:
                raise ValueError('还没有正式事件可以整理成输出：请先提交至少一轮剧情')
            if kind=='storyboard':
                shots=render_storyboard(branch['spec'],chosen)
                rows=[]
                for shot in shots:
                    row=f"镜{shot['shot']:02d}｜{shot['shot_size']}｜{shot['camera']}｜{shot['actor']}：{shot['frame']}"
                    if shot.get('dialogue'):
                        row+=f"｜对白：{shot['dialogue']}"
                    if shot.get('props'):
                        row+=f"｜道具：{shot['props']}"
                    row+=f"｜{shot['rhythm']}｜【来源：{shot['source_event_id']}】"
                    rows.append(row)
                head=f"# {branch['spec'].get('title','')} · 分镜草稿"
                content={'kind':'storyboard','scene_id':sid,'branch_id':bid,'revision':branch['revision'],
                         'event_ids':[e['id'] for e in chosen],'shots':shots,
                         'content':head + "\n\n" + "\n".join(rows),
                         'editable':True,'source':'deterministic_storyboard'}
            else:
                draft_text=render_screenplay(branch['spec'],chosen)
                polished={'text':draft_text,'polished':False}
                if payload.get('polish'):
                    # 作者显式触发才调模型；失败或丢失来源标记则退回确定性草稿
                    polished=polish_screenplay(branch['spec'],chosen,draft_text=draft_text)
                content={'kind':'script','scene_id':sid,'branch_id':bid,'revision':branch['revision'],
                         'event_ids':[e['id'] for e in chosen],
                         'content':polished['text'],
                         'polished':bool(polished.get('polished')),
                         'polish_reason':polished.get('reason'),
                         'draft_content':draft_text if polished.get('polished') else None,
                         'editable':True,
                         'source':'polished_screenplay' if polished.get('polished') else 'deterministic_screenplay'}
            return self._store_output(sid,content,ids)
        content=self.service.output(self.owner,sid,bid,'script' if kind=='screenplay' else kind,ids,base_revision=branch['revision'])
        return self._store_output(sid,content,ids)

    def _store_output(self,sid,content,ids):
        oid=new_id('output'); out={'output_id':oid,**content,'source_event_ids':ids,'editable':True,'created_at':now_iso()}
        with self.repo._connection(write=True) as c:
            c.execute('INSERT INTO director_outputs VALUES (?,?,?)',(oid,sid,self.repo._json(out)))
        return deepcopy(out)
    def list_outputs(self,sid):
        with self.repo._connection() as c:
            return [deepcopy(__import__('json').loads(r[0])) for r in c.execute('SELECT payload_json FROM director_outputs WHERE scene_id=? ORDER BY rowid',(sid,))]
    def get_output(self,oid):
        with self.repo._connection() as c:
            row=c.execute('SELECT payload_json FROM director_outputs WHERE id=?',(oid,)).fetchone()
        if row is None: raise NotFoundError('输出不存在')
        return __import__('json').loads(row[0])
    def update_output(self,oid,payload):
        out=self.get_output(oid); content=payload.get('content')
        if not isinstance(content,(str,list,dict)): raise ValueError('content 必须是文本或结构化对象')
        out['content']=deepcopy(content); out['updated_at']=now_iso()
        with self.repo._connection(write=True) as c:c.execute('UPDATE director_outputs SET payload_json=? WHERE id=?',(self.repo._json(out),oid))
        return out

store=DirectorStore()
