# 测试与实验复现

本目录中的 corpus、case 和示例均为合成数据，不代表作者或任何使用者的真实偏好。testing/runs/ 包含运行产物，默认不上传；克隆仓库后它不存在是正常情况。

## 工程测试

```powershell
New-Item -ItemType Directory -Path runtime -Force | Out-Null
.\.venv\Scripts\python.exe -m pytest --basetemp runtime/pytest-manual --junitxml runtime/pytest.xml
```

该命令验证代码和接口，不会启动付费模型对话，也不使用真实个人经验。部分测试需要本机 HTTP 端口和 MCP 子进程通信，应在允许这些操作的环境运行。

## 固定检索与边界

R01 的准备、执行说明在 [fixed_retrieval/README.md](fixed_retrieval/README.md)。R02 使用新目录，可启动独立服务，不需要把正式 MCP 切到测试库：

```powershell
.\.venv\Scripts\python.exe -m testing.retrieval_round2.run prepare --run-dir testing/runs/my-r02 --expected-backend sqlite-fts5-trigram+field-bigrams-v3 --fresh-server-only
.\.venv\Scripts\python.exe -m testing.retrieval_round2.run execute --run-dir testing/runs/my-r02
```

R02 有一条已知低文字重叠失败，可能以非零状态结束；不能为了成功退出而改预期。先看逐题结果，区分能力失败与基础设施错误。

## 可选的模型应用实验

先准备正常适用案例：

```powershell
.\.venv\Scripts\python.exe -m testing.application_round4.prepare
```

准备程序返回新建目录和 prompt.md。它只建立隔离合成库并冻结材料，不会创建 Codex 对话、调用模型或批准真实经验。先检查生成的提示词，再由你明确选择是否在新会话执行；这一步会使用所选模型的额度。

边界案例可单独准备：

```powershell
.\.venv\Scripts\python.exe -m testing.application_boundaries.prepare --run-prefix my-boundaries
```

每次使用新的 run-prefix，程序拒绝覆盖已有结果。例外、当前要求和来源三个案例的目录相互独立。它不依赖作者未公开的旧 prompt.md，客户端从所在源码仓库发现路径，不需要作者的账号目录。

先做一项，核对实际返回和来源再决定继续。不要把“新会话”当作操作系统级隔离；模型可能读取共享工作区，必须核对可见调用和文件变化。新版公开提示词允许加载公共 decision-context Skill；历史 R07 的旧指令未包含此许可，其偏差不会因此被追溯消除。

测试夹具中的模拟批准仅在独立测试库生效。不要把生成的 bank 注册成正式 MCP，也不要把合成示例批准为真实用户偏好。

历史小规模会话结论见 [应用边界测试摘要](../docs/应用边界测试结果-2026-10-15.md)。原始会话输出不随源码包分发；复现行为实验会生成你的新结果，不能保证与历史模型输出相同。
