"""客户端协议和修改审批测试；模型用替身，目标代码不在宿主机执行。"""
import json
import time
from threading import Event

import pytest
from safety_harness import agent_client as module
from safety_harness.agent_client import AgentClient, ModelError, save


@pytest.fixture
def agent(tmp_path, monkeypatch):
    (tmp_path / 'README.md').write_text('project\n')
    (tmp_path / 'docs').mkdir()
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'test-placeholder')
    instance = AgentClient(tmp_path, 'test-image')
    yield instance
    instance.shutdown()


def wait(agent, sid):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if not agent.active:
            return agent.get(sid)
        time.sleep(.01)
    pytest.fail('Agent did not finish')


def call(name, args, cid='call-1'):
    return {'role':'assistant', 'content':None, 'tool_calls':[{'id':cid, 'type':'function', 'function':{'name':name,'arguments':json.dumps(args)}}]}


def propose(agent, path='README.md'):
    s = agent.get(agent.create()['id'])
    agent.invoke(s, 'propose_edit', {'path':path, 'content':'updated\n', 'reason':'test'})
    return s, s['changes'][0]


def test_tool_conversation_and_resume(agent, monkeypatch):
    answers = iter([call('read_file', {'path':'README.md'}), {'role':'assistant','content':'Read project.'}, {'role':'assistant','content':'Continued.'}])
    monkeypatch.setattr(agent, 'complete', lambda s: next(answers))
    sid = agent.create()['id']
    agent.send(sid, 'read project', ['README.md'])
    s = wait(agent, sid)
    assert s['status'] == 'completed'
    assert s['events'][1]['result']['content'] == 'project\n'
    assert [m['role'] for m in s['messages']] == ['user','assistant','tool','assistant']
    agent.send(sid, 'continue', [])
    assert wait(agent,sid)['messages'][-1]['content'] == 'Continued.'
    assert 'messages' not in agent.public(s)


@pytest.mark.parametrize('path', ['.env', '../README.md', '/etc/passwd', 'results/private/key.json', 'data/generated/key.py', 'docs/.hidden/a.md'])
def test_path_boundary(agent, path):
    with pytest.raises(ValueError): agent.read(path)


def test_symlink_secret_and_frozen_write(agent):
    (agent.root/'docs/link.md').symlink_to(agent.root/'README.md')
    with pytest.raises(ValueError): agent.read('docs/link.md')
    (agent.root/'docs/secret.md').write_text('sk-'+'x'*24)
    with pytest.raises(ValueError): agent.read('docs/secret.md')
    with pytest.raises(ValueError): agent.path('data/controlled/path-01/buggy.py', write=True)
    assert 'docs/link.md' not in agent.files()


@pytest.mark.parametrize('approve', [True,False])
def test_proposal_requires_explicit_decision(agent, approve):
    s, change = propose(agent)
    assert (agent.root/'README.md').read_text() == 'project\n'
    with pytest.raises(ValueError, match='待审查'):agent.send(s['id'], 'continue', [])
    result = agent.decide(s['id'],change['id'],approve)
    assert result['changes'][0]['status'] == ('applied' if approve else 'rejected')
    assert (agent.root/'README.md').read_text() == ('updated\n' if approve else 'project\n')
    with pytest.raises(ValueError): agent.decide(s['id'],change['id'],approve)


def test_approval_preserves_concurrent_edit(agent):
    s, change = propose(agent)
    (agent.root/'README.md').write_text('human changed\n')
    with pytest.raises(ValueError, match='已改变'):agent.decide(s['id'],change['id'],True)
    assert (agent.root/'README.md').read_text() == 'human changed\n'
    agent.decide(s['id'],change['id'],False)


def test_new_file_conflict_and_apply(agent):
    s, change = propose(agent, 'docs/new.md')
    assert not (agent.root/'docs/new.md').exists()
    agent.decide(s['id'],change['id'],True)
    assert (agent.root/'docs/new.md').read_text() == 'updated\n'


def test_stop_prevents_next_tool_and_repairs_protocol(agent, monkeypatch):
    entered, release = Event(), Event()
    def complete(s):
        entered.set();release.wait(3)
        return call('read_file',{'path':'README.md'})
    monkeypatch.setattr(agent,'complete',complete)
    monkeypatch.setattr(agent,'invoke',lambda *args:pytest.fail('Cancelled tool must not run'))
    sid=agent.create()['id'];agent.send(sid,'read',[])
    assert entered.wait(2)
    agent.stop(sid)
    assert agent.public(agent.get(sid))['status']=='stopping'
    release.set();s=wait(agent,sid)
    assert s['status']=='cancelled'
    assert s['messages'][-1]['role']=='tool' and 'interrupted' in s['messages'][-1]['content']


def test_six_call_limit(agent,monkeypatch):
    calls=[]
    def complete(s):
        calls.append(1);return call('list_files',{},str(len(calls)))
    monkeypatch.setattr(agent,'complete',complete)
    sid=agent.create()['id'];agent.send(sid,'inspect',[])
    assert wait(agent,sid)['status']=='limited' and len(calls)==6


def test_restart_repairs_incomplete_tools(agent):
    s=agent.get(agent.create()['id']);s['status']='running';s['messages']=[call('read_file',{'path':'README.md'})]
    save(agent.session_path(s['id']),s)
    restarted=AgentClient(agent.root,agent.image)
    try:
        restored=restarted.get(s['id'])
        assert restored['status']=='interrupted' and restored['messages'][-1]['role']=='tool'
    finally:restarted.shutdown()


@pytest.mark.parametrize('finish', ['tool_calls','length'])
def test_real_sse_decoder_and_truncated_call_guard(agent,monkeypatch,finish):
    packets=[{'choices':[{'delta':{'tool_calls':[{'index':0,'id':'call-x','function':{'name':'read_file','arguments':'{"path":'}}]}}]},
             {'choices':[{'delta':{'tool_calls':[{'index':0,'function':{'arguments':'"README.md"}'}}]},'finish_reason':finish}]},
             {'choices':[],'usage':{'prompt_tokens':20,'completion_tokens':10}}]
    class Response:
        status_code=200
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def iter_lines(self):return iter([b'data: '+json.dumps(p).encode() for p in packets]+[b'data: [DONE]'])
    monkeypatch.setattr(module.requests,'post',lambda *a,**kw:Response())
    s=agent.get(agent.create()['id'])
    if finish=='length':
        with pytest.raises(ModelError, match='不完整'):agent.complete(s)
    else:
        response=agent.complete(s)
        assert json.loads(response['tool_calls'][0]['function']['arguments'])=={'path':'README.md'}
        assert s['usage']=={'prompt_tokens':20,'completion_tokens':10}
    assert s['requests']==1
