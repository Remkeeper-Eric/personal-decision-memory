"""Prepare only; no model session and no real approval operations."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import shutil
from decision_memory.models import Record
from testing.application_round4.prompts import build_prompt
from decision_memory.store import Store, digest
from testing.fixed_retrieval.run import snapshot, write_json, sha, timestamp

PROJECT = Path(__file__).resolve().parents[2]

def main(run_dir=None):
    ROOT = (run_dir or PROJECT / ('testing/runs/R04-application-normal-' + datetime.now().strftime('%Y%m%dT%H%M%S%f'))).resolve()
    if ROOT == (PROJECT / 'testing/runs').resolve() or not ROOT.is_relative_to((PROJECT / 'testing/runs').resolve()):
        raise ValueError('Run must be an independent testing/runs child')
    ROOT.mkdir(parents=True, exist_ok=False)
    before = snapshot(PROJECT / 'vault')
    write_json(ROOT / 'production-before.json', before)
    for folder in ('inputs', 'outputs', 'backups', 'tmp'):
        (ROOT / folder).mkdir()
    client = ROOT / 'client.py'
    shutil.copyfile(Path(__file__).with_name('client.py'), client)
    rows = []
    for name in ('fixed_retrieval/corpus.json', 'retrieval_round2/extra-corpus.json'):
        data = json.loads((PROJECT / 'testing' / name).read_text(encoding='utf-8'))
        assert data['synthetic_only']
        rows.extend(data['records'])
    store = Store(ROOT / 'bank')
    store.init()
    for row in rows:
        relative = store.stage(Record.model_validate(row))
        store.publish(relative, digest(store.draft(relative)[1]))
    write_json(ROOT / 'inputs/corpus.json', {'synthetic_only': True, 'records': rows})
    write_json(ROOT / 'inputs/bank-before.json', {'doctor': store.doctor(),
               'manifest': json.loads(store.manifest_path.read_text(encoding='utf-8'))})
    task = '''一个社区协会需要 Windows 本地活动资料归档小程序。每周整理几次活动附件，按活动日期和资料类别归档并生成清单。交付后由志愿者负责人接手，她不懂编程；每场活动可能要改目标目录、类别名称和几个固定选项。开发者以后每月只能远程支持一次。暂时没有多人同时操作、远程访问或账号权限需求。
请建议合适的交付方式，比较主要替代方案的初始工作量与后续维护负担，并说明交付前怎样验证。只分析，不开发或安装。'''
    (ROOT / 'inputs/task.md').write_text(task + '\n', encoding='utf-8')
    prompt = build_prompt(PROJECT, ROOT, task)
    (ROOT / 'prompt.md').write_text(prompt, encoding='utf-8')
    rubric = '''# R04 正常适用：生成前冻结的检查标准

本轮只验证一个新任务的检索后应用，不验证自主决定何时检索，也不证明个人化增益或全面稳定性。

- 实际调用来自本轮隔离客户端，查询自行组织；正确范围 SYN-team-tools/windows，未读取正式库或其他材料。
- 目标 SYN-M01 v1 实际出现在工具返回中，条件、例外、来源和验证状态完整；只有引用 ID 不算应用。
- 应将非技术接手、常见选项持续变动、开发者支持有限，关联到交付选择和维护取舍；不把通用常识说成记忆带来的已证明增益。
- 倾向常见设置可由接手人操作的简洁入口，并比较脚本或配置文件、Web 等替代方式；GUI 不是唯一强制答案，偏离经验需有题目事实和可观察取舍支持。
- 核对维护者全是开发者且重批处理、一次性不移交的例外不符合本题；不必机械逐字复述所有无关条件。
- 保留初始开发/打包和后续维护负担，避免未经需求支持引入完整 Web 管理系统；提出接手人独立改设置、处理异常和核对归档结果的验证。
- 合成模拟批准不是用户真实批准，unverified 不是效果已验证；external_note 不是用户观点。
- 检索失败时应用记为未观察到；不能因为答案合理而改判记忆链路通过。不补答案重做覆盖原结果。
- 原始输入、完整可见输出及调用结果留档；不保存隐藏思维链。核对生产库、测试清单、冻结输入及代码指纹。共享工作区不是操作系统级访问隔离。
- 与此前同一助手编写样例，且使用熟悉的合成记录，不称为独立盲测。本轮没有空库对照。
- 由用户自行新建会话粘贴提示词。正式行为测试尚未开始，基础设施预检不计为行为成功。结束后交付复核，另行决定下一项。
'''
    (ROOT / 'inputs/rubric.md').write_text(rubric, encoding='utf-8')
    source_files = list((PROJECT / 'src/decision_memory').glob('*.py')) + [Path(__file__), Path(__file__).with_name('client.py'), Path(__file__).with_name('prompts.py')]
    for source in source_files:
        destination = ROOT / 'inputs/source' / source.relative_to(PROJECT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    meta = {'round_id': 'R04-application-normal', 'synthetic_only': True,
            'status': 'prepared_user_will_start_chat', 'created_at': timestamp(), 'human_review': 'pending',
            'model_calls': None, 'model_sessions_started_by_parent': 0, 'thread_id': None,
            'next_case_authorized': False, 'mode': 'instructed isolated retrieval, single normal-use case'}
    write_json(ROOT / 'run.json', meta)
    preflight = ROOT / 'preflight'
    preflight.mkdir()
    shutil.copytree(ROOT / 'bank', preflight / 'bank')
    shutil.copyfile(client, preflight / 'client.py')
    write_json(preflight / 'run.json', {**meta, 'mode': 'infrastructure-only copied bank'})
    write_json(ROOT / 'freeze.json', {'frozen_at': timestamp(), 'files': {
        p.relative_to(ROOT).as_posix(): sha(p) for p in [client, ROOT / 'prompt.md', *(ROOT / 'inputs').rglob('*')]
        if p.is_file()}})
    after = snapshot(PROJECT / 'vault')
    write_json(ROOT / 'production-after-prepare.json', after)
    assert before == after, 'Production changed during preparation'
    print(json.dumps({'status': meta['status'], 'prompt': str(ROOT / 'prompt.md'), 'production_unchanged': True}, ensure_ascii=False))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', type=Path)
    main(parser.parse_args().run_dir)
