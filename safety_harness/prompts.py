"""Only public task information and the buggy target enter generation prompts."""
# 提示构造层：三组共用测试规范，仅逐级增加静态告警和函数上下文。
import json

# 下方英文字符串会原样发送给模型，是实验输入；中文说明放在字符串外。
# 模型只选择输入和受限策略，资源准备与违规断言由可信probe负责。
CONTRACT = """Write a constrained pytest security harness. Return Python source only.
The trusted fixture probe.check(value) calls the target and checks actual security properties.
You choose test inputs and their combinations. Never write assertions, mock functions,
import the target, access files, run commands, or create evidence yourself.
Allowed forms:
def test_safety(probe):
    probe.check("input")
Optional imports: from hypothesis import given, example, strategies as st
Optional @given(value=st.sampled_from([...])) with def test_safety(probe, value).
Only probe.check(...) statements in test bodies. At most 20 tests, string inputs <=2048 chars.
Prefer a few focused tests (at most 8); give each literal input its own test function.
Pass a literal string or the Hypothesis value directly to probe.check.
No assignments, loops, try/except, arithmetic, string concatenation or repetition.
Do not use assertions or other calls in test bodies. Keep the source syntactically complete.
An ordinary exception invalidates the suite; it is not security evidence.
On revision, generated_test_line identifies the failing line in your submitted source.
Remove or replace inputs causing ordinary exceptions; only modify the test source.
Fixtures: path tests expose a public hello.txt under root and private secret.txt outside it.
SQL fixtures contain PUBLIC/PRIVATE rows; only PUBLIC rows are allowed, public name is hello.
Command tests must echo input literally, with no side effects.
Placeholders {MARKER}, {SECRET}, {PUBLIC} resolve to isolated fixture paths.
The oracle checks unexpected creation of {MARKER}, private content, or PRIVATE rows.
These same fixtures and budget apply to every comparison group.
"""


def build_prompt(task, source, analysis, group):
    if group not in {"A", "B", "C"}:
        raise ValueError("Unknown experiment group")
    # 白名单取出公开需求，避免把人工标签、修复版或参考攻击输入泄漏给模型。
    public = {k: task[k] for k in ("requirement", "contract") if k in task}
    prompt = CONTRACT + "\nTask:\n" + json.dumps(public) + "\nTarget:\n" + source
    if group in {"B", "C"}:
        # A只有需求和源码；B、C额外获得同一份Bandit报告。
        prompt += "\nStatic alerts:\n" + json.dumps(analysis["bandit"], ensure_ascii=False)
    if group == "C":
        # C再附加包含敏感调用的函数和文件顶层导入，不发送整棵AST。
        # 三组原本都已看到完整源码；这里检验的是显式整理上下文的作用。
        context = [{"imports": f["imports"], "functions": [fn for fn in f["functions"] if fn["sensitive_calls"]]}
                   for f in analysis["files"]]
        prompt += "\nRisk-localized context:\n" + json.dumps(context, ensure_ascii=False)
    return prompt
