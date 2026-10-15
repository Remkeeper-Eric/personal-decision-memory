# 候选格式

中央库路径由使用者全局 AGENTS.md 的个人决策记忆块指定，默认是安装本系统的仓库内 `vault/`。不要使用项目作者的路径，也不要在当前业务项目另建一个同名库。更换中央库须由用户明确决定，并同步更新 MCP 与指引。

候选只写 `drafts/<id>.md`。ID 用英文字母、数字、下划线或连字符，长度 1–80。以下是字段结构；不要把示例内容保存为用户事实。

```yaml
---
schema_version: 1
id: D-YYYYMMDD-short-name
title: 用一句话表达这次经验
kind: decision_case
base_version: 0
project_scope: []
environments: []
tags: [选型, 维护成本]
aliases: []
sources: [当前用户明确指定的证据或引文位置]
considerations: [用户明确重视的因素]
rationale: 用户为何这样取舍；不确定部分明确保留
applies_when: [满足哪些条件才适用]
exceptions: [哪些情况可能需要改变判断]
action: 后续决策中应做的具体动作
verification: unverified
---

补充案例背景、证据及尚未解决的问题。
```

kind 可用 preference、decision_case、lesson、project_fact、external_note。外部资料不写成 preference。verification 可用 unverified、observed、validated，必须有相应证据。project_scope 与 environments 是硬过滤条件；不确定时先讨论，不能用“全局”消除边界。

修订时 ID 保持不变，base_version 为当前正式版本。列表项不为空，来源、考量和适用条件至少各一项；不允许额外的 approved 字段。空 exceptions 表示尚未列出例外，不证明不存在。
