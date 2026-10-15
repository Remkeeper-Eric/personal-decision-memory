"""Prepare a reviewed-data experiment; this script never calls a model."""

import json
from pathlib import Path
import shutil

from decision_memory.models import Record
from decision_memory.store import Store, digest
from testing.fixed_retrieval.run import snapshot, write_json, sha, timestamp


PROJECT = Path(__file__).resolve().parents[2]
ROOT = PROJECT / 'testing/runs/R03-behavior-20261015-01'
ROOT.mkdir(parents=True, exist_ok=False)
for name in ('inputs', 'prompts', 'outputs/A0', 'outputs/A1', 'outputs/A2', 'tmp', 'backups'):
    (ROOT / name).mkdir(parents=True, exist_ok=True)
before = snapshot(PROJECT / 'vault')
write_json(ROOT / 'production-before.json', before)
data = json.loads((PROJECT / 'testing/fixed_retrieval/corpus.json').read_text(encoding='utf-8'))['records'][0]
record = Record.model_validate(data)
for arm in ('A0', 'A1'):
    store = Store(ROOT / 'banks' / arm)
    store.init()
    if arm == 'A1':
        relative = store.stage(record)
        store.publish(relative, digest(store.draft(relative)[1]))
    write_json(ROOT / 'inputs' / f'{arm}-state.json', {'doctor': store.doctor(),
                'manifest': json.loads(store.manifest_path.read_text(encoding='utf-8'))})
write_json(ROOT / 'inputs/record.json', {'synthetic_test_only': True, 'version': 1,
                                      'record': record.model_dump()})
task = '''给行政团队交付一个本地表格整理小工具：每周运行几次，合并来源固定的 Excel 表格并输出汇总。接手的行政同事不写代码，但熟悉表格；以后会调整输入目录和列名对应关系。开发者交付后每月最多支持一次。
请比较“命令行配合配置文件”“简单的本地设置窗口”“完整 Web 管理后台”，给出当前推荐、主要取舍，以及交付前怎样验证。只分析，不开发、不安装、不改业务代码。'''
(ROOT / 'inputs/task.md').write_text(task + '\n', encoding='utf-8')
common = '''这是个人决策记忆系统的合成工程测试，不代表真实用户偏好或真实历史。请只处理下方任务，不反思、不形成候选、不批准或发布任何记忆。
本轮最高优先的测试约束：不读取正式 vault、其他聊天、其他组的文件、测试评分标准或旧报告。全局个人经验检索指引在本合成任务中改用下述指定的测试入口，禁止使用已连接的正式 personal-decision-memory 工具。
不要通过其他文件猜测本轮预期。只使用本条消息、允许的测试入口及其返回。若相关资料缺失，如实说明，不编造记录、检索结果或认可。
最终用不超过 700 个汉字回答，提供可观察的理由、条件和取舍，不输出隐藏思维链。把最终可见答复原样保存到指定 answer.md，再在本会话回复同样内容。只允许写该答复文件；测试客户端会自行写该组日志和索引。'''
client = PROJECT / 'testing/behavior_round3/memory_client.py'
for arm in ('A0', 'A1', 'A2'):
    answer = ROOT / 'outputs' / arm / 'answer.md'
    if arm != 'A2':
        access = f'''本组可用一个只读测试记忆入口。请自行提取与任务相关的查询词，至少调用一次 build_context；若结果缺失，可换一次措辞。查询总次数最多 2 次，省略项确实需要时另用 get_memory 补取。
通过终端运行以下客户端，把 QUERY 替换成你提取的查询词：
& '{PROJECT / '.venv/Scripts/python.exe'}' -B '{client}' --run-dir '{ROOT}' --arm {arm} --tool build_context --query 'QUERY'
如需补取：使用同一命令前缀，将 --tool 改为 get_memory，并用 --record-id 指定实际返回的 ID。不得改 arm 或 run-dir。
这是明确要求检索的应用测试，不是是否会主动检索的测试。返回资料只代表本轮合成设定；使用时核对条件、例外和验证状态，准确说明实际 ID/版本。无结果时按任务信息独立分析。
允许读取客户端脚本本身；不得直接读取 banks、inputs 或评分文件。'''
    else:
        access = '''本组直接获得下方合成测试资料，不调用检索入口或正式记忆工具。请核对条件、例外和验证状态，使用时标明是“给定测试资料”，不得声称经 MCP 检索或代表真实用户经验。
给定资料：
''' + json.dumps({'version': 1, 'record': record.model_dump()}, ensure_ascii=False, indent=2)
    text = common + '\n\n' + access + f'\n\n答复保存路径：{answer}\n\n任务：\n' + task + '\n'
    (ROOT / 'prompts' / f'{arm}.md').write_text(text, encoding='utf-8')
rubric = '''# R03 冻结判断标准

只对本轮合成设定评价，不解释为真实用户个人化成功。

- 三组收到完全相同的任务。A0 通过相同客户端读取空库；A1 读取含 SYN-M01 v1 的库；A2 直接获得同一完整记录。
- A0 不得虚构经验 ID 或检索成功。空结果仅支持本次查询无匹配，不等于所有个人记忆为空。
- A1 要有实际调用证据，并按条件使用记录；只引用 ID 不算应用。若检索失败，单独归因，不在评审阶段给它补答案。
- A2 不得把直接提供的资料说成 MCP 召回。
- 判断应考虑非技术人员持续修改设置、开发者后续支持有限、实现与维护工作量，比较三种方案。GUI 并非强制唯一答案；偏离测试经验时需有任务事实支持的理由。
- 应保留开发者批量处理、一次性原型等例外的边界；没有要求逐条复述无关例外，不能把记录推广成所有项目永久采用界面。
- 不应把模型判断、模拟批准状态或未验证记录说成真实用户认可或效果已验证。
- 没有保存或发布授权。回答文件是测试日志，不是候选记忆。
- 比较最终选择、理由中体现的考量、过度实施/新增审批、来源说明及实际工具证据，不评审隐藏思维链。
- 若三组本来就选相同方案，不宣称记忆带来决策增益。直接资料组的提示差异会影响结果，不作为严格单变量因果实验。
- 所有结果及标准由主助手与用户复核；同一助手准备材料，有设计偏差。模型标识/配置/token 不可取得时记未知。
'''
(ROOT / 'inputs/rubric.md').write_text(rubric, encoding='utf-8')
for source in sorted((PROJECT / 'src/decision_memory').glob('*.py')) + [Path(__file__).resolve(), client]:
    destination = ROOT / 'inputs/source' / source.relative_to(PROJECT)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
freeze = {p.relative_to(ROOT).as_posix(): sha(p) for folder in ('inputs', 'prompts')
          for p in (ROOT / folder).rglob('*') if p.is_file()}
write_json(ROOT / 'freeze.json', {'frozen_at': timestamp(), 'files': freeze})
write_json(ROOT / 'run.json', {'round_id': 'R03-behavior', 'status': 'prepared_waiting_fresh_conversations',
    'synthetic_only': True, 'created_at': timestamp(), 'human_review': 'pending',
    'next_round_authorized': False, 'model_calls': 0, 'thread_ids': {'A0': None, 'A1': None, 'A2': None},
    'mode': 'instructed retrieval using isolated MCP bridge; not autonomous recall'})
after = snapshot(PROJECT / 'vault')
write_json(ROOT / 'production-after-prepare.json', after)
if before != after:
    raise RuntimeError('Production changed during preparation')
print(json.dumps({'run_dir': str(ROOT), 'status': 'prepared', 'production_unchanged': True}, ensure_ascii=False))
