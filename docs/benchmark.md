# Benchmark 运行与计分

项目目前支持两层评测，二者不能混算。

## 受控动态基准

使用已有的 30 组人工构造缺陷版/修复版样本，其中 6 组用于开发，24 组用于评测。运行模型生成测试，再在 rootless、无网络、非特权容器中执行。三组都获得源码：A 直接生成，B 增加 Bandit 告警，C 再增加 AST 函数上下文。

单轮为 24 × 3 = 72 次试验。每次最多生成一次、修订两次。核心指标是**同一测试在缺陷版触发违规、在修复版通过**的配对复现率。可运行率、修复版有效判定数及误报率另报。普通测试异常不能计为漏洞。

```bash
# 已安装依赖、构建 v0.2 镜像，并在根目录 .env 配置密钥。
.venv/bin/safety-harness doctor --image localhost/bjtu-safety-harness:0.2
.venv/bin/safety-harness experiment \
  --out results/private/benchmark-new \
  --data data/controlled --split eval --repeats 1 \
  --model deepseek-flash --input-price 2 --output-price 8 \
  --budget-cny 100 --ledger results/private/budget.json \
  --image localhost/bjtu-safety-harness:0.2
.venv/bin/python scripts/audit_model_run.py results/private/benchmark-new
.venv/bin/python scripts/verify_model_evidence.py results/private/benchmark-new
```

模型标识和价格为 2026-10-25 核对值，价格使用高峰、输入全部未命中的保守口径；以后运行须重新核对官网。沿用共享预算账本，不要删除账本以重置预算。新一轮使用新目录；中断续跑使用相同目录和参数，复用已保存响应。

网络失败不是一次成功响应，也不能悄悄忽略其潜在调用次数。续跑前应逐次记录失败所属 trial，保守算作一次请求；若总请求超过三次，整组匹配的 A/B/C 样本从预算内比较中剔除，同时保留全量结果。禁止通过换目录或只挑成功样本得到更高分。

本轮 `results/private/benchmark-20261025` 另保存源码指纹、预算起点和基础设施事件。可使用以下命令从原始日志重建公开统计，无需再次调用模型或执行目标：

```bash
.venv/bin/python scripts/finalize_benchmark.py \
  results/private/benchmark-20261025 --out results/benchmark-20261025
```

`finalize_benchmark.py` 要求该批次的 `provenance.json` 和完整证据；不完整时拒绝生成完整分数。它检查原始响应与测试一致性、目标/镜像哈希、反馈来源及配对结论，但不是对安全判据的独立人工复核。

## SecurityEval 外部静态诊断

来源：[SecurityEval 官方仓库](https://github.com/s2e-lab/SecurityEval)，固定提交 `6f4fb70f782c6d47b02ea24341e8ef8c1eb04a6a`。该版本 `dataset.jsonl` 有 121 个样本，分析对象为原始 `Insecure_code` 字段，保留全部样本，不运行任何目标代码。

脚本只读取固定数据文件及下载来源元数据。原始数据保存在忽略目录，不随本项目公开分发；上游仓库未见根目录许可证文件，后续分发前须进一步确认许可。

```bash
.venv/bin/python scripts/securityeval_static_benchmark.py \
  --dataset build/securityeval-20261025/dataset.jsonl \
  --source build/securityeval-20261025/source.json \
  --out results/private/securityeval-static-new
```

`source.json` 包含 `repository`、`commit`、`url`，数据文件 SHA-256 由脚本独立记录。运行输出目录必须不存在，避免覆盖历史诊断。

静态指标含义：

- Bandit 任意告警：样本有至少一条告警，可能与其标注漏洞无关。
- AST 敏感调用：项目支持的函数内敏感调用名称被匹配，不是数据流分析或漏洞确认。
- 任一线索：上面两个集合的并集。
- CWE 精确匹配：Bandit 告警 CWE 与样本编号 CWE 相等；不处理父子分类，也不证明告警位置正确，仅用于诊断。

此数据只有上游标为不安全的代码，尚未独立核验其标签，也没有安全负例，因此不能计算可靠的准确率、精确率或误报率。本轮没有外部样本动态复现、没有模型参与该静态诊断，不声称得到官方排行榜分数。

要继续外部动态评测，应先为选定样本定义威胁模型、入口和环境，完成最小适配与正常功能测试，建立人工核验的触发证据及修复版，再冻结适配器后运行 A/B/C。公开代码可能已进入模型训练数据，也应作为结论限制披露。
