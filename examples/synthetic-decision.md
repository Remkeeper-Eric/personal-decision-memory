---
schema_version: 1
id: DEMO-maintenance
title: 合成演示：交接前检查维护负担
kind: decision_case
base_version: 0
project_scope: [demo-project]
environments: []
tags: [维护成本, 交接]
aliases: [操作交接]
sources: [虚构演示，不代表项目作者或使用者的真实偏好]
considerations: [接手人能否独立修改设置, 后续支持时间]
rationale: 这个虚构案例用于展示带条件的经验格式，需要在具体任务中重新判断。
applies_when: [向其他人移交一个需要持续调整设置的小工具]
exceptions: [一次性且不再维护的演示可采用更简单的交付方式]
action: 比较交接人的操作负担与实现成本，并让接手人独立试用。
verification: unverified
---

只用于 runtime/demo-vault 中的演示。请勿将本示例作为真实个人经验批准到中央库。
