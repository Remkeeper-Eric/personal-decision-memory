# 固定检索验收 R01

这些是合成工程测试数据，不是用户真实经验。直接调用 Store，不运行模型、不测试 Codex 自主检索、不访问生产发布接口。

从项目根目录执行，先冻结再运行。prepare 返回本轮的绝对目录，将其用于 execute：

```powershell
& .\.venv\Scripts\python.exe -B testing\fixed_retrieval\run.py prepare
& .\.venv\Scripts\python.exe -B testing\fixed_retrieval\run.py execute --run-dir '上一步返回的绝对目录'
```

所有测试库、模拟批准、索引、事务、临时文件及日志均位于新建的 testing/runs/ 轮次目录。备份目录也位于该目录，本轮不执行导出。程序拒绝覆盖已有轮次或在非 testing/runs/ 目录执行。

inputs/ 保存冻结语料、题目、每题实际记录变体以及源代码副本与哈希。execute 核对冻结文件与代码后执行，一次完成便停止；不自动重试、加别名、修复检索、创建下一轮或写个人记忆。

每题 output.json 保存完整 Store 输入输出、异常、耗时与检查。state-before.json、state-after.json 和 setup.json 保存临时清单、状态构造过程及文件哈希。生产 vault 仅做运行前后文件哈希快照；发现变化会停止并报告，快照不构成操作系统级写入隔离。

report.md 提供逐题结果，results.json 是机器可读报告。进程退出码：0=全部题目符合预期，1=存在题目失败或证据不足，2=运行设施错误/冻结校验或生产变化。探索项失败也保留为失败，不并入基本边界的通过数。

本轮只有三条记录，同一项目最多两条可检索记录，不能据此证明大量记录下的前五条排序可靠，也不能证明模型理解例外或遵循当前用户要求。已知接口能返回 external_note 类型，不代表模型会正确使用它。
