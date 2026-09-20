from tempfile import TemporaryDirectory
from pathlib import Path
from director_core.engine import DirectorStore, ConflictError

def scene(store):
    return store.create_scene({'title':'测试会议','location':'室内','actors':[{'id':'a','name':'甲','role':'发起人','location':'室内'},{'id':'b','name':'乙','role':'董事','location':'室内'},{'id':'c','name':'丙','role':'法务','location':'室内'}],'facts':[{'id':'private','label':'私密事实','known_by':['c']},{'id':'public','label':'公开事实','known_by':['a','b','c']}],'items':[{'id':'doc','name':'授权书','holder':'a'}]})

def test_shared_world_draft_preview_commit_visibility():
    with TemporaryDirectory() as tmp:
        s=DirectorStore(Path(tmp)/'x.db'); sid=scene(s)['scene_id']; assert {x['id'] for x in s.visible_facts(sid,'a')} == {'public'}
        d=s.create_draft(sid,{}); assert s.current_state(sid)['revision']==0; p=s.preview_draft(d['draft_id']); assert p['proposed_state'] and s.current_state(sid)['events']==[]
        result=s.commit_draft(d['draft_id'],0,'key',1); assert result['revision']==1

def test_revision_lock_branch_and_idempotency():
    with TemporaryDirectory() as tmp:
        s=DirectorStore(Path(tmp)/'x.db'); sid=scene(s)['scene_id']; d=s.create_draft(sid,{})
        try:s.commit_draft(d['draft_id'],0,'bad',1)
        except ConflictError:pass
        else:raise AssertionError('preview required')
        s.preview_draft(d['draft_id'],1); one=s.commit_draft(d['draft_id'],0,'ok',1); two=s.commit_draft(d['draft_id'],0,'ok',1); assert one==two
        b=s.create_branch(sid,{'name':'试演'}); assert b['state']['revision']==1
        d2=s.create_draft(sid,{'branch_id':b['branch_id']}); s.preview_draft(d2['draft_id'],1); s.commit_draft(d2['draft_id'],1,'b',1); assert s.current_state(sid,'main')['revision']==1 and s.current_state(sid,b['branch_id'])['revision']==2

def test_edit_transfer_output_persistence():
    with TemporaryDirectory() as tmp:
        p=Path(tmp)/'x.db'; s=DirectorStore(p); sid=scene(s)['scene_id']; d=s.create_draft(sid,{}); events=d['candidate_events']; events[0]['action']='甲交付授权书'; events[0]['transfer']={'item_id':'doc','to_actor_id':'b'}
        s.patch_draft(d['draft_id'],{'candidate_events':events,'locks':['events.0.action'],'version':1}); s.preview_draft(d['draft_id'],2); s.commit_draft(d['draft_id'],0,'k',2); out=s.create_output(sid,{'type':'storyboard','source_event_ids':[events[0]['id']]}); s2=DirectorStore(p); assert s2.get_output(out['output_id'])['source_event_ids']==[events[0]['id']]
