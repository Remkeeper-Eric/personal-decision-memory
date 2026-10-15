# 对话内审核与记录

安装目录和中央库由全局 AGENTS.md 指定。以下命令在安装目录运行，或使用该目录 Python 的绝对路径；--vault 始终显式指定中央库，不根据当前业务项目猜路径。用户只审核对话内容，无需操作终端或页面。

## 展示前只读预览

尚未获得保存授权时，不写文件。将完整 Markdown 记录按 UTF-8 传给标准输入：

```powershell
# 将完整记录作为标准输入；不要把本示例文字当成用户记录。
<完整记录的 UTF-8 标准输入> | .\.venv\Scripts\python.exe -m decision_memory --vault <中央库> preview -
```

preview - 会解析字段、补齐默认值并规范化 Markdown，返回 content、id、version、sha256、vault_id 和建议的 drafts/ 相对路径，不写库、草稿或索引。PowerShell 应将本次进程的 $OutputEncoding 和 [Console]::OutputEncoding 都设为 [System.Text.UTF8Encoding]::new($false)，避免 Windows PowerShell 的输入管道或输出解码丢失中文；Python 可加 -X utf8。完整展示 content 对应的所有字段和正文，并保留这次返回的指纹及库 ID。技术元数据可用中文解释；不能省略来源、范围、例外或验证状态，不另行润色待保存正文。

已有用户明确要求生成的草稿，用 preview drafts/<id>.md 读取其实际字节。陈旧 base_version 会报错，须先修订再展示。

## 当前用户明确批准后

若候选未落盘，将刚才的 content 按 UTF-8 原样写入中央库 drafts/<id>.md，或用 stage 序列化同一记录；不能覆盖未核对的人工草稿。然后运行：

```powershell
.\.venv\Scripts\python.exe -m decision_memory --vault <中央库> approve drafts/<id>.md --sha256 <展示时的sha256> --vault-id <展示时的vault_id> --confirmed --approval-message <当前用户确认原话>
```

批准必须在展示之后来自真实用户，且指向该版本；--confirmed 不能用来推断用户意图。没有明确批准就不调用 approve。内容变化、库不一致或正式版本变化会失败；重新展示实际新版本并等待批准，不拿新计算的哈希重试绕过。相同有效内容重复批准不会增加版本。

确认文本记入私有清单的 approval 字段，标为 agent-transcribed，不是独立认证证据。不要将含真实记录或确认文本的清单发布到 GitHub。保存后通过只读 get_memory 检查 ID/版本/内容，确认当前范围仍有效；必要时 CLI doctor 排查，不把检索无匹配解释成保存失败或整个库为空。

## 停用

先读取并向用户说明将停用的具体记录及版本；用户明确要求停用后，使用读取时的哈希和同一中央库 ID：

```powershell
.\.venv\Scripts\python.exe -m decision_memory --vault <中央库> revoke <记录ID> --sha256 <读取时的sha256> --vault-id <同一库ID> --confirmed --approval-message <当前用户停用指令原话>
```

停用保留历史，不等于永久删除。不得擅自停用冲突经验。旧网页入口仅为兼容保留，不参与默认对话流程。
