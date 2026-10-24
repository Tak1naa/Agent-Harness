# 数据卡

controlled包含30组人工构造的缺陷/修复配对，每类10组；各类01—02为开发集，共6组，其余24组为冻结评测。作者：本项目在AI辅助下编写，需团队复核；创建于2026-10-20。样本为本项目原创模板变体，未复制外部仓库代码。本目录原创样本以CC0-1.0提供（https://creativecommons.org/publicdomain/zero/1.0/），不改变其他仓库文件的许可。未使用真实隐私数据。

变体涵盖直接拼接、路径解码、前缀校验缺陷，shell调用及不完整过滤，SQL字符串拼接及不完整转义等。模板共享、样本短小、同类分割可能导致模式泄漏；结果仅适用于本受控集，后续须引入独立来源项目并按项目/模板划分。

manifest记录来源、修改说明和划分；freeze记录全部文件sha256。`verify-data`检查内容变更。参考测试与fixed.py永不进入生成模型prompt。reference.py是人工参考测试，不能计作模型成果。

`generation_tasks.json`是12个正常功能任务，每类4个。实际模型代码尚未生成。generate-targets保留全部响应并初始化unknown标签；两个不同成员独立核验后填写review.json中的label、evidence、reviewer_1、reviewer_2、status=reviewed。无一致结论则unknown，不能删除困难或无漏洞样本。generated与controlled分别汇总。

## 2026-10-22真实生成批次

采用`generation_tasks_v2.json`的12项不同正常需求，输出在`generated/`，全部保留，语法检查通过。仅完成代码生成，动态执行、功能验收与两名成员复核仍待完成，当前标签全部unknown。原`generation_tasks.json`保留为早期方案，不能误作本批次输入。复核步骤见`docs/模型代码双人复核.md`。
