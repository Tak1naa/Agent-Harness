---
name: Harness 项目客户端
description: 以会话、工具过程与显式修改审批为中心的浅色项目客户端
colors:
  accent: "#266954"
  ink: "#282b2a"
  muted: "#6c706d"
  paper: "#ffffff"
  rail: "#f3f3f0"
  soft: "#f8f8f6"
  line: "#e4e5e1"
  selected: "#e3e7df"
  diff-add: "#e8f4e3"
  diff-remove: "#fbece7"
  focus: "#6b9b86"
typography:
  headline:
    fontFamily: '"Noto Sans CJK SC", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif'
    fontSize: "27px"
    fontWeight: 650
    lineHeight: 1.5
    letterSpacing: "-0.025em"
  body:
    fontFamily: '"Noto Sans CJK SC", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif'
    fontSize: "13px"
    lineHeight: 1.65
  message:
    fontFamily: '"Noto Sans CJK SC", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif'
    fontSize: "12px"
    lineHeight: 1.95
  label:
    fontFamily: '"Noto Sans CJK SC", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif'
    fontSize: "10px"
  code:
    fontFamily: "ui-monospace, monospace"
    fontSize: "10px"
    lineHeight: 1.9
rounded:
  control: "6px"
  item: "7px"
  message: "12px"
  composer: "14px"
spacing:
  compact: "6px"
  action-gap: "8px"
  inset: "12px"
  section: "24px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.paper}"
    rounded: "{rounded.control}"
    padding: "7px 11px"
  button-default:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "7px 11px"
  session-selected:
    backgroundColor: "{colors.selected}"
    textColor: "{colors.ink}"
    rounded: "{rounded.item}"
    padding: "10px 12px"
  file-search:
    backgroundColor: "#f5f7f1"
    rounded: "{rounded.control}"
    padding: "8px 11px"
  tool-message:
    backgroundColor: "#fafbf8"
    rounded: "{rounded.item}"
  composer:
    backgroundColor: "#fafbf8"
    rounded: "{rounded.composer}"
---

# Design System: Harness 项目客户端

## Overview

**Creative North Star: "Operate · 项目会话台"**

用户选择的 Operate 方向以代码工作为依据：清楚的会话层级、可展开的工具过程、明确的修改决策。浅色中性底与克制的绿色强调建立安静的阅读环境，界面密度服务于持续操作。

设计依据当前客户端源码提取。主要通过细边框、浅底色与位置区分区域，有限阴影用于输入区和覆盖式面板。中文采用本机系统字体，代码采用等宽字体，不依赖外部字体资源。

**Key Characteristics:**
- 会话和任务输入构成视觉主轴。
- 工具结果与修改差异可逐项检查。
- 系统中文字体、浅色中性层级和少量绿色强调。

## Colors

### Primary
沉稳绿色 `accent` 用于应用修改等确认操作；深色发送按钮形成输入区的动作锚点。强调色不用于把工具返回结果包装成安全结论。

### Neutral
`paper` 是聊天底色；`rail` 是会话侧栏；`soft` 承载轻量操作背景。`ink` 和 `muted` 区分主体与辅助信息，`line` 分隔固定区域，`selected` 标记当前会话。差异以 `diff-add`、`diff-remove` 的浅底结合原始加减符号阅读，`focus` 标记键盘焦点。

## Typography

系统中文无衬线字体贯穿正文、控件与导航。欢迎标题采用 headline；根字号采用 body，聊天正文采用 message。小型状态文字为 9–10px，常用按钮为 11px。标题层级保持紧凑，不把欢迎标题尺度用于每条消息。

差异与文件预览采用 code；消息代码块另使用 11px、1.8 行高。品牌字母标识使用 Georgia，主界面品牌文字为 19px。移动端欢迎标题降为 23px。当前紧凑状态字号是已实现值，不代表已完成全面可读性或无障碍认证。

## Layout

默认以视口高度 `100dvh` 组织三栏：左侧 230px、中央 `minmax(380px, 1fr)`、右侧 340px。聊天、会话列表和检查面板各自滚动；聊天内容最大宽度 850px，输入区最大宽度 900px，欢迎内容最大宽度 650px。顶部栏为 69px，默认聊天留白为 28px × 38px。

- 至少 1550px：三栏改为 250px、`minmax(500px, 1fr)`、390px；中央水平留白为 60px。
- 至多 1180px：左侧 210px、中央 `minmax(320px, 1fr)`；右侧变为 350px 的覆盖面板，按需打开。
- 至多 650px：中央单列，左侧变为 260px 的覆盖侧栏，右侧宽度为 `min(360px, 100vw)`；顶部栏为 61px，聊天水平留白为 20px，输入区水平留白为 13px。

间距按用途取值，源码没有统一的严格 8px 网格。输入区留在聊天区下方，面板不挤走主要任务流程。

以上布局适用于 `/` 客户端。`/research` 是独立研究 surface，继续由 `app.css` 控制其统计、表格和案例布局；不共享客户端三栏规则，也不以研究页旧的 760px 断点指导客户端。

## Elevation & Depth

聊天和检查面板通过白色、微暖灰绿色底与细边界区分。输入区使用很轻的阴影 `0 3px 12px #1b291207`。右侧覆盖面板使用 `-6px 0 30px #25331912`，移动会话侧栏使用 `5px 0 25px #25331918`，表达覆盖关系。不存在全局“无阴影”的规则。

## Shapes

常规控件与差异面板使用 control 圆角；会话条目、代码块与工具记录使用 item；用户消息使用 message；输入容器使用 composer。输入容器比工具记录更柔和，区别持续输入与过程证据。连接点和流式指示形状小而克制。

## Components

**操作按钮。** 常规按钮白底细边框；确认操作为绿色实底；轻量面板切换采用浅底。发送为独立的深色方形图标按钮，停止以文字和暖色提示。禁用状态降低透明度并取消操作指针。

**输入与文件搜索。** 多行输入容器聚焦时改变边框，文本域自身不重复显示外轮廓；其他按钮、输入、链接和折叠标题保留 2px 焦点环、3px 偏移。文件搜索为浅底窄边框。引用文件以可移除的小标签呈现。

**会话与面板导航。** 会话条目显示标题、时间和状态，选中使用独立底色。右侧“文件／修改／操作”以底部线条和文字区分选中项，修改数量仅计待审批项。

**工具记录。** 折叠标题包含动作、目标和文字状态，展开显示真实参数和返回内容；运行指示与流式光标使用 1 秒的步进动画。建议按钮仅有 0.15 秒颜色过渡。系统要求减少动态效果时禁用动画与过渡。

**差异审批。** 提案呈现路径、理由、状态和保留原始行前缀的增删差异，随后提供应用与拒绝按钮。状态改变后移除待审批操作。空结果、连接失败、工具失败和中断都使用明确文字反馈。

## Do's and Don'ts

### Do:
- Do 保留选中、运行、失败、待确认和中断的文字状态。
- Do 将代码、参数与差异放入可滚动的等宽阅读区。
- Do 在窄屏通过可开合侧栏保留文件引用与审批入口。

### Don't:
- Don't 用研究统计卡片代替会话首页。
- Don't 仅依靠颜色表达工具结果或审批状态。
- Don't 将研究页的排版、断点或图表规则套到会话客户端。
