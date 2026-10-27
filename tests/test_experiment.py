from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path
from safety_harness.experiment import run_experiment, summarize_run
from safety_harness.io import write_json

ROOT=Path(__file__).resolve().parents[1]
class FakeModel:
    model='offline-test-double'
    budget=SimpleNamespace(input_rate=1, output_rate=1)
    calls=0
    def complete(self,messages):
        self.calls+=1
        return {'code':'def test_safety(probe):\n    probe.check("../secret.txt")\n',
                'usage':{'prompt_tokens':10,'completion_tokens':10},'response_model':self.model}

def test_batch_resume_and_no_fixed_feedback(tmp_path):
    model=FakeModel()
    def execute(target,*args,**kwargs):
        return {'status':'pass' if target.name=='fixed.py' else 'violation','duration_seconds':1}
    with patch('safety_harness.experiment.preflight',return_value={'image_id':'offline-mock'}), \
         patch('safety_harness.experiment.run_harness',side_effect=execute), \
         patch('safety_harness.experiment.analyze_project',return_value={'bandit':{'findings':[]},'files':[]}):
        result=run_experiment(ROOT/'data/controlled',tmp_path,model,'dev',1)
        assert result['records']==18 and result['complete_abc_blocks']==6
        assert model.calls==18
        run_experiment(ROOT/'data/controlled',tmp_path,model,'dev',1)
        assert model.calls==18
    for p in tmp_path.glob('*/messages-0.json'):
        assert 'fixed.py' not in p.read_text()

def test_all_attempt_durations_and_unknown_labels(tmp_path):
    write_json(tmp_path/'result.json',{'kind':'model_experiment','dataset':'generated','id':'x','repeat':0,
        'split':'generated','group':'A','ground_truth':'unknown','candidate_violation':True,
        'confirmed':False,'false_positive':False,'runnable':True,
        'buggy':{'status':'violation','duration_seconds':3},
        'attempts':[{'observed':{'duration_seconds':2},'usage':{}},{'observed':{'duration_seconds':3},'usage':{}}]})
    row=summarize_run(tmp_path)['groups'][0]
    assert row['duration_seconds']==5 and row['unknown_labels']==1
    assert row['confirmed_rate'] is None and row['false_positive_rate'] is None


def test_unresolved_fixed_runs_are_not_reported_as_safe(tmp_path):
    for i, status in enumerate(['pass', 'violation', 'harness_error', 'not_run']):
        write_json(tmp_path / f'{i}.json', {
            'kind': 'model_experiment', 'dataset': 'controlled', 'split': 'dev',
            'id': str(i), 'repeat': 0, 'group': 'A', 'confirmed': False,
            'false_positive': status == 'violation', 'runnable': False,
            'fixed': {} if status == 'not_run' else {'status': status},
        })
    row = summarize_run(tmp_path)['groups'][0]
    assert row['negative_denominator'] == 4
    assert row['false_positive_rate'] == 0.25
    assert row['negative_valid_evaluations'] == 2
    assert row['negative_unresolved'] == 2
    assert row['observed_false_positive_rate'] == 0.5
