"""HTTP边界、任务状态及核心函数接线；不在宿主机执行样本。"""
import json
from pathlib import Path
import shutil
import time

import pytest
from starlette.testclient import TestClient

from safety_harness import web

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client(tmp_path, monkeypatch):
    shutil.copytree(ROOT / 'data/controlled', tmp_path / 'data/controlled')
    shutil.copytree(ROOT / 'results/benchmark-20261025', tmp_path / 'results/benchmark-20261025')
    monkeypatch.delenv('DEEPSEEK_API_KEY', raising=False)
    with TestClient(web.create_app(tmp_path)) as c:
        yield c


def submit(client, data):
    csrf = client.get('/api/bootstrap').json()['csrf']
    return client.post('/api/jobs', json=data, headers={'X-Harness-CSRF': csrf})


def wait_job(client, job_id):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        job = client.get('/api/jobs/' + job_id).json()
        if job['status'] not in {'queued', 'running'}:
            return job
        time.sleep(.02)
    pytest.fail('Job did not finish')


def test_page_assets_and_no_key_disclosure(client, monkeypatch):
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'unit-test-secret-never-expose')
    boot = client.get('/api/bootstrap')
    assert boot.json()['key_configured']
    assert 'unit-test-secret' not in boot.text
    page = client.get('/')
    assert page.status_code == 200 and '新会话' in page.text
    assert '案例工作台' in client.get('/research').text
    assert client.get('/assets/client.js').status_code == 200
    assert "frame-ancestors 'none'" in page.headers['content-security-policy']
    assert client.get('/assets/app.js').status_code == 200
    assert client.get('/.env').status_code == 404
    assert client.get('/api/cases/path-01').json()['files']['buggy.py'].startswith('import')


def test_host_csrf_and_cross_origin(client):
    assert client.get('/api/bootstrap', headers={'Host':'attacker.example'}).status_code == 400
    assert client.post('/api/jobs', json={'kind':'analyze','case_id':'path-01'}).status_code == 403
    csrf = client.get('/api/bootstrap').json()['csrf']
    assert client.post('/api/jobs', json={'kind':'analyze'}, headers={'X-Harness-CSRF':csrf, 'Origin':'https://attacker.example'}).status_code == 403


@pytest.mark.parametrize('payload', [
    {'kind':'shell','command':'echo bad'},
    {'kind':'analyze','case_id':'../../.env'},
    {'kind':'analyze','case_id':'path-01','variant':'../../.env'},
    {'kind':'run','case_id':'path-01','harness':"import os\nos.system('true')"},
    ['not', 'an', 'object'],
])
def test_reject_unbounded_operations(client, payload):
    assert submit(client, payload).status_code == 400


def test_body_limit_and_invalid_json(client):
    headers={'X-Harness-CSRF':client.get('/api/bootstrap').json()['csrf']}
    assert client.post('/api/jobs',content='x'*64001,headers=headers).status_code == 413
    assert client.post('/api/jobs',content='oops',headers=headers).status_code == 400


def test_real_static_analysis_and_persisted_job(client):
    response = submit(client, {'kind':'analyze','case_id':'command-01'})
    assert response.status_code == 202
    job = wait_job(client, response.json()['id'])
    assert job['status'] == 'completed'
    assert job['result']['bandit']['findings']
    assert client.get('/api/jobs').json()[0]['id'] == job['id']


def test_pair_uses_same_test_and_keeps_reference_separate(client, monkeypatch):
    seen=[]
    monkeypatch.setattr(web,'preflight',lambda image: {'rootless':True})
    def runner(target,harness,category,**kwargs):
        seen.append((target.name,harness.read_text(),category,kwargs['image']))
        return {'status':'violation' if target.name=='buggy.py' else 'pass'}
    monkeypatch.setattr(web,'run_harness',runner)
    response=submit(client,{'kind':'run','case_id':'path-01'})
    job=wait_job(client,response.json()['id'])
    assert job['status']=='completed' and job['result']['confirmed']
    assert job['result']['kind']=='manual_validation'
    assert seen[0][1:] == seen[1][1:]


def test_isolation_failure_never_runs_target(client, monkeypatch):
    def fail(image): raise web.IsolationError('Rootless Podman unavailable')
    monkeypatch.setattr(web,'preflight',fail)
    monkeypatch.setattr(web,'run_harness',lambda *a,**kw: pytest.fail('Must not execute'))
    assert client.get('/api/environment').json()['status']=='blocked'
    job=wait_job(client,submit(client,{'kind':'run','case_id':'sql-01'}).json()['id'])
    assert job['status']=='blocked' and 'result' not in job


def test_model_configuration_and_experiment_wiring(client, monkeypatch):
    assert submit(client,{'kind':'experiment'}).status_code == 400
    monkeypatch.setenv('DEEPSEEK_API_KEY','test-placeholder')
    assert submit(client,{'kind':'experiment','budget':101}).status_code == 400
    assert submit(client,{'kind':'experiment','split':'other'}).status_code == 400
    calls=[]
    def experiment(data,out,model,split,repeats,image):
        calls.append((split,repeats,image,model.model,model.budget.limit))
        return {'records':18,'groups':[],'complete_abc_blocks':6}
    monkeypatch.setattr(web,'run_experiment',experiment)
    job=wait_job(client,submit(client,{'kind':'experiment','split':'dev','budget':50}).json()['id'])
    assert job['status']=='completed' and job['total']==18
    assert calls == [('dev',1,web.IMAGE,'deepseek-flash',50)]


def test_reports_and_absent_private_evidence(client):
    report=client.get('/api/reports/benchmark-20261025').json()
    assert report['summary']['records']==72
    assert report['summary']['groups'][0]['confirmed']==20
    assert client.get('/api/reports/benchmark-20261025/trial?case=path-01&group=A&repeat=0').status_code==404
    assert client.get('/api/reports/benchmark-20261025/trial?case=path-01&group=../../.env').status_code==400
    assert client.get('/api/jobs/not-a-job').status_code==400


def test_busy_guard_and_interrupted_state(client, monkeypatch):
    wb=client.app.state.workbench
    wb.active='busy'
    assert submit(client,{'kind':'analyze','case_id':'path-01'}).status_code==409
    wb.active=None
    job_id='a'*32
    web.write_json(wb.folder(job_id)/'job.json',{'id':job_id,'kind':'run','params':{},'status':'running'})
    restarted=web.Workbench(wb.root)
    try: assert restarted.get_job(job_id)['status']=='interrupted'
    finally: restarted.pool.shutdown()


def client_action(client, action, data):
    csrf=client.get('/api/client/info').json()['csrf']
    return client.post('/api/client/actions/'+action,json=data,headers={'X-Harness-CSRF':csrf})


def test_client_http_boundaries_and_missing_key(client):
    info=client.get('/api/client/info').json()
    assert not info['key_configured'] and 'messages' not in info
    assert client.post('/api/client/actions/create',json={}).status_code==403
    headers={'X-Harness-CSRF':info['csrf'],'Origin':'https://evil.example'}
    assert client.post('/api/client/actions/create',json={},headers=headers).status_code==403
    s=client_action(client,'create',{}).json()
    assert client.get('/api/client/sessions/'+s['id']).json()['status']=='idle'
    assert client_action(client,'send',{'session_id':s['id'],'text':'hi'}).status_code==400
    assert client.get('/api/client/file?path=.env').status_code==400
    assert client.get('/api/client/file?path=data/controlled/path-01/buggy.py').status_code==200
    assert client_action(client,'decide',{'approve':'yes'}).status_code==400
    assert client_action(client,'create',[]).status_code==400
    assert client.post('/api/client/actions/create',content='x'*64001,headers={'X-Harness-CSRF':info['csrf']}).status_code==413


def test_client_http_model_tool_and_approval(client,monkeypatch):
    monkeypatch.setenv('DEEPSEEK_API_KEY','test-placeholder')
    agent=client.app.state.agent
    def complete(s):
        return {'role':'assistant','content':'修改待审批。','tool_calls':[{'id':'edit-1','type':'function','function':{'name':'propose_edit','arguments':json.dumps({'path':'docs/ui-test.md','content':'# Test\n','reason':'HTTP契约验证'})}}]}
    monkeypatch.setattr(agent,'complete',complete)
    sid=client_action(client,'create',{}).json()['id']
    assert client_action(client,'send',{'session_id':sid,'text':'propose test note'}).status_code==200
    deadline=time.monotonic()+5
    while agent.active and time.monotonic()<deadline:time.sleep(.01)
    session=client.get('/api/client/sessions/'+sid).json()
    assert session['status']=='awaiting_approval' and 'messages' not in session
    path=agent.root/'docs/ui-test.md'
    assert not path.exists()
    cid=session['changes'][0]['id']
    assert client_action(client,'decide',{'session_id':sid,'change_id':cid,'approve':True}).status_code==200
    assert path.read_text()=='# Test\n'
    assert client.get('/api/client/file?path=docs/ui-test.md').json()['content']=='# Test\n'
