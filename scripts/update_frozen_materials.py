"""Derive dated presentation copy and status notes from verified frozen results."""
import json,re
from pathlib import Path

f=json.loads(Path('results/frozen-20261022/analysis.json').read_text())
g={x['group']:x for x in f['primary_summary']['groups']};n=g['A']['denominator']
old=json.loads(Path('scripts/presentation_content.json').read_text())
texts=[
'各位老师好，我们的项目是基于程序分析的代码智能体安全性测试Harness构建方法。中期聚焦一个问题：在相同模型和调用上限下，静态分析给出的风险位置与函数上下文，能否帮助模型生成更有效的Python安全测试？',
'目前进度落后于开题安排，我们保留题目，收敛到路径穿越、命令注入和SQL注入。Bandit提供静态疑点，实际是否违规还需要执行证据。因此先完成局部分析和动态验证，符号执行、自动修复与跨语言延期，并如实说明范围调整。',
'流程从Python代码开始，复用Bandit扫描，再用AST整理风险函数、签名和导入。模型生成测试输入，也可以使用Hypothesis扩展边界。统一探针负责调用入口、临时资源和安全断言，避免把错误断言当作攻击成功。代码在无网络、非特权容器内执行并限制资源。自主实现集中在上下文组织、探针、证据记录和对照实验。主实验使用直接API，DeepSeek Harness仅完成固定版本SDK和MCP启动验证，完整模型工具回合还未验证。',
'请看路径穿越案例。人工参考测试输入点点斜杠secret.txt。缺陷版直接拼接路径，读到公共目录外的随机哨兵，探针记录违规。修复版规范化路径并校验边界，同一测试不再触发。现在播放二十秒的真实记录回放。这证明执行和判定链路能够工作，模型效果则由下一页对照实验判断。',
f'正式评测包含二十四个冻结样本，每组重复三次，共二百一十六次试验。A组直接生成，B组增加告警，C组再增加AST上下文。网络失败保守计入调用上限，剔除超额试验所在的整个匹配块后，各组保留{n}次，分别配对复现{g["A"]["confirmed"]}、{g["B"]["confirmed"]}和{g["C"]["confirmed"]}次。全量结果也单独保留。这里是人工模板和单模型条件下的观察，不能宣称普遍提升。失败案例中，程序只拦截以点点斜杠开头的路径，但三组某轮都没想到在前面加点斜杠来绕过。因此测试通过只代表这次没找到违规，不能直接证明代码安全。报告同时公布误报、未判定、覆盖率、Token与成本。',
'目前原型、三类参考案例和冻结对照已经完成。十二份正常需求的真实模型输出也全部保留，但仍待两人独立标签和正常功能验收。负责人主抓方法与集成，动态负责人负责隔离与案例，数据负责人负责统计与材料。我们也明确单文件、模板相似和同进程探针的局限，成员须理解并复核AI辅助产物。',
'中期前要补齐双人复核和两轮真人计时。之后先引入独立来源样本，建立功能与安全双重判据，再研究输入到敏感调用的局部依赖上下文。实验保留强直接生成基线，做去反馈、去依赖的消融并比较成本。只有失败分析证明路径约束是主要障碍时，再开展有界符号执行试验。谢谢各位老师。'
]
texts[5]+='三十组人工样本只用于可控验证，不能记作模型生成成果。正常需求输出即使安全或功能不完整，也都纳入记录，未知标签不会被删除。'
for x,t in zip(old,texts):x['speech']=t
old[4]['title']='冻结评测结果与失败案例'
old[5]['body'][0]='已完成：原型、参考案例与 216 次冻结试验'
old[5]['body'][2]='局限：单文件、统一入口、人工模板相似\n12 份真实输出待双人复核与功能验收'
old[6]['body']=['中期前：完成双人复核、正常功能与计时演练','中期后：独立来源样本，功能与安全双重判据','研究重点：输入到敏感调用的局部依赖上下文','强基线、消融、成本比较后，再决定符号执行']
old[2]['body'][1]='02  模型选择测试输入，支持 Hypothesis 扩展'
old[4]['body']=[f'主要比较：每组 {n} 次',f'A {g["A"]["confirmed"]}/{n}，B {g["B"]["confirmed"]}/{n}，C {g["C"]["confirmed"]}/{n}',f'216 次全量记录，排除 {len(f["excluded_matched_blocks"])} 个超预算匹配块','失败：path-10 三组某轮均漏掉 ./../secret.txt']
Path('scripts/presentation_content_frozen.json').write_text(json.dumps(old,ensure_ascii=False,indent=2)+'\n')
count=len(re.findall(r'[\u4e00-\u9fff]',''.join(texts)))
assert 900<=count<=1100,count
speech=f'# 五分钟答辩讲稿（2026-10-22）\n\n正文约{count}个汉字。7页预算合计300秒，包含20秒静音回放，讲述可与录像并行。真人演练尚未完成，目标4分40秒至4分50秒，按实际语速删减。\n\n'
speech+='\n\n'.join(f'## 第{i+1}页 · {x["time"]}秒\n\n{x["speech"]}' for i,x in enumerate(old))
Path('deliverables/逐页讲稿-20261022.md').write_text(speech+'\n')
qa=Path('deliverables/答辩问答.md').read_text()
qa=qa.replace('当前还没有算法效果优于基线的实验证据。','正式结果见2026-10-22冻结统计；小样本描述性差异尚不能作为普遍算法优势。')
qa=qa.replace('模型效果必须等待冻结A/B/C结果。','模型效果应看冻结A/B/C结果，并同时考虑成本、模板相似与失败。')
start=qa.index('**6.');end=qa.index('**7.')
qa=qa[:start]+f'**6. 模型实验结果是什么？**\n冻结批次完成216次。保守计入网络失败请求，剔除超上限匹配块后，每组{n}次，A/B/C配对复现分别为{g["A"]["confirmed"]}/{n}、{g["B"]["confirmed"]}/{n}、{g["C"]["confirmed"]}/{n}。全量结果与排除项均留存。不能把重复试验当成独立样本，也不能把描述性差异写成显著提升。\n\n'+qa[end:]
qa=qa.replace('当前参考评测24例里仅5例有分支，均值50%，其余19例零分支；不能把它写成总体100%覆盖。','正式模型结果逐组报告有效覆盖分母；参考验证与模型评测分开。零分支样本不记作100%分支覆盖。')
qa+='\n**15. 网络失败是否破坏公平比较？**\n所有不确定请求均保守计入调用次数。超过三次上限的整个A/B/C匹配块退出主要比较，同时展示全量结果。规则是首次网络失败后的透明处理，不伪装成原始预注册；未来应在协议中预定义基础设施重试与随机块重跑规则。\n\n**16. 中期后最优先研究什么？**\n先补独立数据和功能判据，再研究输入到敏感调用的局部依赖上下文，以强基线、消融和每次成功成本衡量增益。符号执行是否值得接入由失败类型决定。\n'
Path('deliverables/答辩问答-20261022.md').write_text(qa)
print(json.dumps({'speech_hanzi':count,'slides':len(old),'seconds':sum(x['time'] for x in old)},ensure_ascii=False))
