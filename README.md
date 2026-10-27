# 基于程序分析的代码智能体安全性测试 Harness 构建方法

面向大创中期的研究原型。研究问题：相同模型、工具和调用上限下，Bandit 告警与 AST 函数上下文能否提高 Python 安全测试的有效性？原始 `react_agent_deepseek.py` 保留为探索记录，不用作隔离或漏洞判定。

## 会话客户端

完成下方依赖安装后，执行 `bash scripts/start_web.sh`，打开 <http://127.0.0.1:8765/>。
左侧管理会话，中间给 Agent 下任务，右侧查看文件、工具记录和修改差异；修改需点击确认才能写入。
已接通 DeepSeek 流式对话、真实静态分析和容器配对测试。研究统计在侧栏“研究与评测”中。

这是本项目有界 Agent 的浏览器客户端，不是官方 DeepSeek Harness SDK 会话或原生桌面安装包。
密钥仍在 `.env` 中配置；不提供宿主机 Shell，动态目标只在原有隔离容器中运行。
启动、操作、预算和能力边界见[客户端使用](docs/客户端使用.md)。

## 已完成与待完成

- 已实现：Bandit/AST 分析、受限 pytest/Hypothesis 测试语法、rootless Podman 执行、真实副作用判据、JSON/CSV、CLI、MCP stdio、预算与断点续跑。
- 已验证：30 组人工构造配对样本，缺陷版均复现、修复版均不再触发。这是参考测试的工程验证，不能证明模型效果，也不等于30个独立真实项目。
- DeepSeek Harness：SDK `0.2.1rc2` 独立环境启动成功，加载 MCP 插件；MCP 工具协议另有测试。尚未进行带模型的工具选择、生成及完整智能体回合。
- 已开展：真实 API 的开发集 A/B/C 小批量试验，原始日志分别保存于 `results/private/pilot-20261022` 和 `results/private/pilot-20261022-v2`；不同开发轮次不得合并为正式评测。
- 冻结评测已完成：216次全量试验，A/B/C分别62/72、63/72、68/72配对复现。7次网络失败保守计入调用上限，排除3个超上限匹配块后，主要比较为61/69、62/69、67/69。证据链和冻结源码哈希核验通过；小样本描述性结果不代表普遍提升。
- 已生成12份不同正常需求的真实模型输出，全部保留；动态执行、正常功能验收、双人独立标签、真人计时仍待完成。
- 最新材料位于 [`deliverables/中期答辩-20261027/`](deliverables/中期答辩-20261027/)：7页五分钟答辩PPT、6页中期报告、逐页讲稿及展示方案，不含视频。2026-10-22材料及不带日期的早期材料保留为历史快照；应按日期区分实验口径。冻结统计见`results/frozen-20261022/analysis.json`，参考文献见`docs/参考文献与阅读顺序.md`。

## 安装与无 Key 验证

Python 3.12 用于编排（建议与已验证版本一致），需要 rootless Podman。不要用 sudo 启动 runner。

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock.txt
.venv/bin/python -m pip install --no-deps -e .
podman build -t localhost/bjtu-safety-harness:0.2 -f containers/Containerfile containers
.venv/bin/safety-harness verify-data
.venv/bin/safety-harness doctor --image localhost/bjtu-safety-harness:0.2
.venv/bin/pytest -m 'not container'
RUN_CONTAINER_TESTS=1 HARNESS_TEST_IMAGE=localhost/bjtu-safety-harness:0.2 .venv/bin/pytest tests/test_container.py
.venv/bin/safety-harness reference --out results/reference-new --image localhost/bjtu-safety-harness:0.2
.venv/bin/safety-harness summarize results/reference-new
```

`doctor` 检查 rootless 与镜像，每次 `run` 在启动前再次核验无网络、只读根文件系统、非特权、全部 capability 删除和资源限制。隔离失败立即停止，不能退回宿主机运行。测试容器不挂载源码仓库、个人目录或密钥，只挂载当前目标代码与测试。CPU=1、内存256MiB、PID64，执行默认20秒。

v0.2新增生成测试错误行反馈。旧API默认镜像仍为v0.1以保留原有复现入口；新的开发与评测命令应显式传入v0.2。已有v0.1镜像不要覆盖，各批次以记录的镜像ID为准。

## API Key 粘贴位置

项目根目录 `.env` 的第二行 `DEEPSEEK_API_KEY=` 后面粘贴。该文件权限应为600、已忽略；不存在时复制 `.env.example` 为 `.env`，不要覆盖已有配置。CLI 仅在本地加载它，环境变量优先。不要把 Key 粘贴到源码、聊天或 PPT。

```bash
cp -n .env.example .env
chmod 600 .env
# 在编辑器中填写 .env 第二行。正式运行前按官网核对模型标识和单价。
.venv/bin/safety-harness experiment --help
```

首次仅跑开发集，每组3个上限内调用、每样本1次重复。用 `MODEL`、`INPUT_PRICE`、`OUTPUT_PRICE` 环境变量提供当前模型标识及每百万Token人民币价格（均需明确填写，仓库不猜测价格）。

```bash
.venv/bin/safety-harness experiment --split dev --repeats 1 --out results/private/pilot \
  --model "$MODEL" --input-price "$INPUT_PRICE" --output-price "$OUTPUT_PRICE" --budget-cny 10 \
  --image localhost/bjtu-safety-harness:0.2
# 测量实际使用和预留预算后，再运行正式24样本×3组×3重复，共216个trial。
.venv/bin/safety-harness experiment --split eval --repeats 3 --out results/private/controlled-eval \
  --model "$MODEL" --input-price "$INPUT_PRICE" --output-price "$OUTPUT_PRICE" --budget-cny 100 \
  --image localhost/bjtu-safety-harness:0.2
.venv/bin/safety-harness generate-targets --tasks data/generation_tasks_v2.json --out data/generated \
  --model "$MODEL" --input-price "$INPUT_PRICE" --output-price "$OUTPUT_PRICE" --budget-cny 100
# 全部12份代码保留，两名不同成员填写各 review.json，未知项仍纳入分母。
.venv/bin/safety-harness experiment --corpus generated --data data/generated --repeats 3 \
  --out results/private/generated-eval --model "$MODEL" \
  --input-price "$INPUT_PRICE" --output-price "$OUTPUT_PRICE" --budget-cny 100 \
  --image localhost/bjtu-safety-harness:0.2
```

所有调用共用 `results/private/budget.json`。预算按UTF-8输入字节上界和最大输出保守预留；失败请求不退款、不自动重试。此账本不替代平台账单，价格变化后新建批次且仍保留旧账本总预算。断点续跑复用已保存的响应，参数/数据变化需新输出目录。正式对比须完成匹配的A/B/C块，先检查summary的 `complete_abc_blocks`；未完成块不可用于组间结论。

## 三个可复现案例

```bash
.venv/bin/safety-harness analyze data/controlled/path-01/buggy.py --out results/path-analysis.json
.venv/bin/safety-harness run data/controlled/path-01/buggy.py data/controlled/path-01/reference.py --category path --out results/path-bad.json
.venv/bin/safety-harness run data/controlled/path-01/fixed.py data/controlled/path-01/reference.py --category path --out results/path-fixed.json
# command-01 / sql-01 同理，category分别为 command / sql。
```

`violation` 表示可信探针记录真实越界读、无害命令标记或私有SQL行，并由安全异常使pytest失败。普通异常、语法错误、Mock命中、导入失败与assert False不能直接算漏洞。原始证据在 `results/reference/`，回放在 `deliverables/`。

## 编排与研究边界

主实验采用直接API，严格控制三组调用与工具预算。DeepSeek Harness接入仅用于外部编排探索，不能把它自己的shell sandbox当作本项目安全边界。详见 `integrations/deepseek-harness/README.md`。模型只产出输入选择和Hypothesis策略，目标导入、临时资源与断言由可信 `probe` 提供；这是首阶段的范围收敛，不声称已能生成任意pytest夹具。

各类样本都统一到 `handle(value: str, root: str)`，仅单文件局部函数分析。参见 `docs/研究协议.md`、`docs/推进与分工.md`、`data/README.md`。中期材料的工程结果与模型结果严格分开。原始立项PDF含个人信息，不进入交付包或公开仓库。

## 重建冻结统计

2026-10-24已为核心源码添加中文注释，未改变提示词或执行逻辑，但源码的字节哈希已变化。重建2026-10-22批次时，请在原交付包解压出的目录中执行下列命令；不要用注释后的源码覆盖历史哈希或在旧输出目录续跑。原始源码也保存在该批次的`source_snapshot/`目录中，已有镜像和交付包保持不变。

```bash
.venv/bin/python scripts/finalize_frozen.py
.venv/bin/python scripts/update_frozen_materials.py
```

重建不调用API、不执行目标代码。原始记录位于`results/private/frozen-eval-20261022`，其目录在Git中忽略，但纳入本次本地交付ZIP供核验。网络失败的处理规则是在首次失败后续跑前记录，未伪称原始预注册；全量与剔除后的结果并列报告。密钥及含个人信息的立项原件不进入交付包。

## 中文注释阅读入口

先读`safety_harness/experiment.py`了解总流程，再读`analyze.py`、`prompts.py`和`model.py`了解模型获得的信息。`runner.py`负责隔离运行，`containers/worker.py`负责容器内测试，`containers/security_probe.py`解释三类违规如何取证。`policy.py`说明模型生成的测试为什么只能使用受限语法。

## Benchmark 试跑（2026-10-25）

新增一轮24个受控评测样本 × A/B/C × 1次重复：配对复现分别为20/24、22/24、22/24；不与2026-10-22三次重复的冻结批次混算。这次C组未比B组多复现样本。另在固定版本SecurityEval的121份原始代码上完成静态诊断，Bandit有告警48份，联合AST有线索53份；这不是公开集上的动态漏洞检出率或排行榜分数。

结果和限制见[本轮结果](results/benchmark-20261025/README.md)，复跑及计分方法见[benchmark说明](docs/benchmark.md)。原始输出位于忽略目录`results/private/benchmark-20261025`及`results/private/securityeval-static-20261025`。
