"""Shared public prompt, independent of previous private run artifacts."""

def build_prompt(project, root, task, limit=800):
    client = root / "client.py"
    return f'''这是个人决策记忆系统的一次合成应用测试，不代表真实用户偏好或真实项目历史。只处理本条任务，不反思、不生成候选、不批准或发布记忆。

本轮测试约束优先于项目中通常使用正式个人记忆入口的指引：本题只可通过下方指定的隔离客户端查询。禁止调用已连接的正式 personal-decision-memory 工具，禁止读取正式 vault、其他聊天、旧报告、其他测试组、bank、inputs、preflight、评分标准或准备脚本。允许读取本提示词文件、指定客户端本身、已加载的公共 decision-context Skill 及客户端实际返回的结果；不从别处寻找预期答案。

你需自行组织与任务相关的查询词，至少调用一次 build_context。无相关结果时可换一次措辞，查询总次数最多两次；确实需要的 omitted 项可另用 get_memory。只根据实际返回核对来源、条件、例外、项目范围和验证状态。无匹配、工具失败和校验失败须区分，不编造记忆或检索成功。

在 PowerShell 运行，QUERY 由你自行填写：
$env:PYTHONUTF8='1'
$env:PYTHONIOENCODING='utf-8'
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
& '{project / '.venv/Scripts/python.exe'}' -B '{client}' --tool build_context --query 'QUERY'

客户端会启动本机只读 MCP 子进程，所有库、索引、临时文件和调用日志限定在本次测试目录。若受执行权限限制，用 exec_command 的 require_escalated 仅运行这条隔离命令；不要换成正式工具。若已启动的客户端超过 30 秒仍无输出，先停止该挂起进程，同一查询最多重试一次，不根据等待猜测返回结果。基础设施重试与换查询分别说明；仍失败则如实结束本次测试。

补取时使用同一个客户端，将 --tool 改为 get_memory 并以 --record-id 指定实际返回的 ID。不得修改客户端、源代码、库或指令。

请用不超过 {limit} 个汉字给出可见答复：推荐、主要取舍、所用记录的实际 ID/版本及条件判断、交付验证方法。不要输出隐藏思维链，不声称合成记录是用户真实认可或已验证有效的偏好。若未取得相关记录，按题目事实作答并如实说明。

将最终答复原样保存到 '{root / 'outputs/answer.md'}'，然后在本对话回复同样内容。除此之外不要主动写其他文件；客户端自行记录调用日志。完成即停止，不修复检索、不替自己评分、不继续测试。

任务：
{task}
'''
