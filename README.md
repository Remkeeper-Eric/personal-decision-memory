# Personal Decision Memory · 个人决策记忆

让 Codex 在后续项目中参考**你审核过的考量、经验和例外**，逐步减少重复的决策错误。

这是一个本地 Markdown 记忆库、人工审核页面和只读 MCP 服务。它使用运行时检索帮助判断，不修改模型权重，不在日常聊天中偷偷归纳习惯。当前为 **0.1.0 实验版**，MIT 许可。

## 工作方式

1. 你明确要求反思，先讨论遗漏、取舍和适用边界。
2. 你明确要求形成候选，Codex 才保存草稿。
3. 你在本机页面确认具体版本，候选才成为正式记忆。
4. 后续项目通过只读 MCP 检索，核对条件、例外和当前要求后应用。

“反思一下”“分析不错”均不等于保存或批准。当前要求优先，外部资料不代表你的个人观点。项目结束也不会自动复盘或写入经验。

## 环境要求

- **Windows + Python 3.12**：本版实际验证环境；需要 SQLite 支持 FTS5/trigram，官方 Python 发行版通常提供，遇到错误见[故障排查](docs/故障排查.md)。
- 使用 Codex 集成时，需要支持本地 MCP 与 Skills 的 Codex 环境。
- Obsidian 可选，用于查看 Markdown；不需要一直打开。
- 本服务不要求额外的模型 API Key。Codex 自身的账号、模型使用和费用仍按你所用的产品配置。

目前推荐从源码进行可编辑安装。未发布到 PyPI；不要用同名第三方包代替本仓库。

## 快速开始：Windows PowerShell

从本 GitHub 仓库下载并解压源码，或复制仓库自己的克隆地址进行克隆。进入**包含 pyproject.toml 的仓库根目录**后执行：

~~~powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\python.exe -m decision_memory init
.\.venv\Scripts\python.exe -m decision_memory doctor
~~~

没有 `py` 命令时，可使用已确认版本为 3.12 的 `python` 创建虚拟环境。上述命令不需要激活环境，也不需要修改系统 PowerShell 执行策略。依赖安装需要访问你的 Python 包源。

`init` 创建仓库内的私有 `vault/`，不会导入作者的个人数据或示例。新用户的正式记忆为空是正常状态。此时你已经可以使用本地命令和审核页；下一步是可选的 Codex 全局集成。

### 连接到你的 Codex

先预览将要修改的位置：

~~~powershell
.\.venv\Scripts\python.exe scripts/install_codex.py
~~~

确认预览符合你的配置后，由你执行安装：

~~~powershell
.\.venv\Scripts\python.exe scripts/install_codex.py --apply
~~~

安装会更新你自己的 Codex 全局 AGENTS 受管区块、一个 `personal-decision-memory` MCP 入口，以及 `decision-context`、`review-personal-decision` 两个用户级 Skill。其他配置保留，原文件备份到 `runtime/install-backups/`。同名非本项目 Skill 或非本项目服务器不会被强行覆盖。

安装后重载 MCP 或重新打开 Codex，在新会话发送：

> 检查 personal-decision-memory 是否连接成功。只调用只读查询，说明实际返回和警告；不要生成、保存或批准记忆，不要把一次查询无匹配解释成整个库为空。

预期能看到 `search_memory`、`get_memory`、`build_context`。配置存在不等于当前聊天已经加载，需实际调用核对。[自定义路径、安装恢复及配置说明](docs/安装与配置.md)

## 日常怎样使用

发现值得纠正的回答时：

> 反思这次回答：我重视的是……，你遗漏了……。先分析遗漏、合理取舍和适用边界，与我讨论，不保存。

讨论满意，并且你确实希望留下经验时：

> 把刚才确认的结论形成待审核候选，写明来源、适用条件、例外和以后应改变的动作，不替我批准。

然后打开审核页面：

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\打开审核页面.ps1
~~~

此处 Bypass 只用于这次脚本进程。阅读页面上的候选和具体版本，按页面要求确认；**最后的批准必须由你自己操作**。修改候选后，必须重新阅读并确认新版本。关闭浏览器不会停止服务，停止命令为：

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\停止审核服务.ps1
~~~

候选格式见 [record-format.md](skills/review-personal-decision/references/record-format.md)。项目范围和环境是硬过滤条件；单项目经验不应未经讨论变成全局偏好。

后续实质决策前，已安装指引要求 Codex 检索相关经验，说明关键 ID/版本及适用条件。它仍依赖模型遵守指引；如果没调用工具、调用失败或没有匹配，应如实说明，不能声称“已学习”。

## 先用演示库试一下

[合成示例](examples/synthetic-decision.md)不代表任何人的真实偏好。下列命令只向独立演示库生成草稿，不会批准到中央库：

~~~powershell
.\.venv\Scripts\python.exe -m decision_memory --vault runtime/demo-vault init
.\.venv\Scripts\python.exe -m decision_memory --vault runtime/demo-vault stage examples/synthetic-decision.md
.\.venv\Scripts\python.exe -m decision_memory --vault runtime/demo-vault doctor
~~~

此时演示库仍没有正式记忆，草稿不参与普通检索。如需体验审核页面，在另一个终端运行下列前台服务，用它输出的本机地址打开页面，体验后按 Ctrl+C 停止。请只在演示库审核示例：

~~~powershell
.\.venv\Scripts\python.exe -m decision_memory --vault runtime/demo-vault review --session-file runtime/demo-review-session.json
~~~

这个演示不会将 Codex 的正式 MCP 改接到演示库。

## 本地查询、备份与 Obsidian

~~~powershell
.\.venv\Scripts\python.exe -m decision_memory search '维护成本' --project '你的稳定项目名' --environment windows
.\.venv\Scripts\python.exe -m decision_memory context '维护成本与交接条件' --project '你的稳定项目名' --environment windows
.\.venv\Scripts\python.exe -m decision_memory export runtime/backup-1.zip
.\.venv\Scripts\python.exe -m decision_memory restore runtime/backup-1.zip runtime/restored-vault
~~~

备份文件名必须是新文件，恢复目录必须为空。导出包含正式记录和历史，不包含草稿；若要保留草稿，也需自行备份。默认本地备份不能替代另一块磁盘上的备份。

Obsidian 选择“打开文件夹作为仓库”，打开安装本系统的仓库内 `vault/`。不要直接编辑正式历史正文以更改已批准经验；修订应另生成候选并重新审核。

## 已验证什么，尚未验证什么

- 有工程测试覆盖候选、版本指纹、撤销、范围、并发、恢复、安装保护及 HTTP/MCP 接口。
- 少量独立 Codex 会话中观察到正常应用、识别例外和当前要求优先；外部资料测试判断正确，但有读取范围偏差，详见[行为测试摘要](docs/应用边界测试结果-2026-10-15.md)。
- 检索为 SQLite FTS5、中文双字片段和有限的软件交接同义词表。它不是通用语义检索；低文字重叠仍可能漏检。
- 小规模库每次查询从校验后的文件重建索引，尚未做大规模性能优化。
- 字符预算不是 token 预算；记录获批也不等于效果已验证。
- 尚未证明会在所有真实任务中自主触发检索，或相对于模型常识持续改善个人决策。[待验证问题](docs/待真实使用验证的问题.md)

## 数据与安全边界

真实记忆、候选和索引在 `vault/`；运行日志、配置备份在 `runtime/`；原始测试会话在 `testing/runs/`。它们默认被 Git 忽略，也不会进入发布脚本生成的源码包。若自定义路径，需自己维护对应的备份和忽略规则。

记忆存储在本机；实际检索内容会进入当前 AI 会话，仍受所用模型服务的数据政策影响。审核页只监听本机回环地址，带随机路径的审核 URL 和安装备份都不要公开。工作流审批不能隔离拥有同一系统写权限的其他程序。

## 开发与发布

~~~powershell
New-Item -ItemType Directory -Path runtime -Force | Out-Null
.\.venv\Scripts\python.exe -m pytest --basetemp runtime/pytest-manual --junitxml runtime/pytest.xml
.\.venv\Scripts\python.exe scripts/prepare_release.py --check
.\.venv\Scripts\python.exe scripts/prepare_release.py
~~~

源码包和 SHA256 文件写入 `dist/`，不执行 Git 提交或上传。仓库附带 Windows CI 配置，上传后由 GitHub 执行；本地验证不能代替云端 CI 结果。

更多说明：[安装与配置](docs/安装与配置.md) · [故障排查](docs/故障排查.md) · [测试复现](testing/README.md) · [贡献说明](CONTRIBUTING.md) · [发布说明](docs/发布与隐私.md) · [更新记录](CHANGELOG.md)

## 许可

代码采用 [MIT License](LICENSE)。源码包不包含项目作者的个人记忆或原始会话；合成测试数据均明确标注为演示或测试用途。
