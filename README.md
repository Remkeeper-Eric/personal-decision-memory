# Personal Decision Memory · 个人决策记忆

让 Codex 在后续项目中参考**你审核过的考量、经验和例外**，逐步减少重复的决策错误。

这是一个本地 Markdown 记忆库、对话内人工审核流程和只读 MCP 服务。它使用运行时检索帮助判断，不修改模型权重，不在日常聊天中偷偷归纳习惯。当前为 **0.1.0 实验版**，MIT 许可，已支持对话内明确授权后记录。

## 工作方式

1. 你明确要求反思，先讨论遗漏、取舍和适用边界。
2. 讨论收敛后，Codex 在对话中展示准备记录的完整内容，请你审核；未要求落盘时只展示、不写文件。
3. 你明确批准该版本并要求记录后，Codex 才保存正式记忆，无需打开页面。你也可以单独要求保存待审草稿，草稿不参与检索。
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

`init` 创建仓库内的私有 `vault/`，不会导入作者的个人数据或示例。新用户的正式记忆为空是正常状态。此时你已经可以使用本地命令；下一步是可选的 Codex 全局集成。

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

讨论收敛后，Codex 会在对话里展示准备记录的完整内容，包括来源、适用范围、条件、例外、理由、以后应改变的动作和未验证部分，并请你审核。你无需打开页面或复制命令。

如果你满意，并且确实希望正式保存，直接回复：

> 审核通过，按刚才这版记录。

Codex 收到这次明确授权后才保存，并回报记录 ID、版本及核查结果。“分析不错”不等于批准保存。若你要求修改，先展示修改后的版本，再由你批准；不能在批准后自行润色、扩大范围或补充例外并直接记录。

你仍可以只讨论、不保存，也可以只要求生成待审核草稿。讨论中展示候选不会自动写入文件；草稿尚未获批时不作为个人经验使用。

候选格式见 [record-format.md](skills/review-personal-decision/references/record-format.md)。项目范围和环境是硬过滤条件；单项目经验不应未经讨论变成全局偏好。

后续实质决策前，已安装指引要求 Codex 检索相关经验，说明关键 ID/版本及适用条件。它仍依赖模型遵守指引；如果没调用工具、调用失败或没有匹配，应如实说明，不能声称“已学习”。

## 先用演示库试一下

[合成示例](examples/synthetic-decision.md)不代表任何人的真实偏好。下列命令只向独立演示库生成草稿，不会批准到中央库：

~~~powershell
.\.venv\Scripts\python.exe -m decision_memory --vault runtime/demo-vault init
.\.venv\Scripts\python.exe -m decision_memory --vault runtime/demo-vault stage examples/synthetic-decision.md
.\.venv\Scripts\python.exe -m decision_memory --vault runtime/demo-vault doctor
~~~

此时演示库仍没有正式记忆，草稿不参与普通检索。可以只读查看完整待审内容：

~~~powershell
.\.venv\Scripts\python.exe -m decision_memory --vault runtime/demo-vault preview drafts/DEMO-maintenance.md
~~~

这个演示不会批准示例，也不会将正式 MCP 改接到演示库。如要体验保存，先在对话里要求审核这条演示候选，并在看完后明确授权“只记录到演示库”。本地批准入口及只读标准输入预览见[对话审核命令](skills/review-personal-decision/references/conversation-approval.md)；这些命令由 Codex 按你的授权操作，日常使用不需要你手工执行。

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

- 有工程测试覆盖候选、版本指纹、撤销、范围、并发、恢复、安装保护及 HTTP/MCP 接口；对话审核命令另检查未确认、改后批准、错误库和陈旧版本等边界。
- 少量独立 Codex 会话中观察到正常应用、识别例外和当前要求优先；外部资料测试判断正确，但有读取范围偏差，详见[行为测试摘要](docs/应用边界测试结果-2026-10-15.md)。
- 检索为 SQLite FTS5、中文双字片段和有限的软件交接同义词表。它不是通用语义检索；低文字重叠仍可能漏检。
- 小规模库每次查询从校验后的文件重建索引，尚未做大规模性能优化。
- 字符预算不是 token 预算；记录获批也不等于效果已验证。
- 尚未证明会在所有真实任务中自主触发检索，或相对于模型常识持续改善个人决策。[待验证问题](docs/待真实使用验证的问题.md)

## 数据与安全边界

真实记忆、候选和索引在 `vault/`；运行日志、配置备份在 `runtime/`；原始测试会话在 `testing/runs/`。它们默认被 Git 忽略，也不会进入发布脚本生成的源码包。若自定义路径，需自己维护对应的备份和忽略规则。

记忆存储在本机；实际检索内容会进入当前 AI 会话，仍受所用模型服务的数据政策影响。对话内授权依赖 Codex 正确识别真实用户的明确批准，程序中的 --confirmed 和确认文字只是调用方声明，不是独立的人类身份认证。程序会核对内容指纹、库 ID 和版本，并保留确认原话，但不能据此宣称验证了用户本人。安装备份、正式清单和确认文本不要公开。

旧审核页及启停脚本仅为兼容保留，默认流程不启动、不要求使用。无论采用哪个入口，都不能隔离拥有同一系统写权限的其他程序。

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
