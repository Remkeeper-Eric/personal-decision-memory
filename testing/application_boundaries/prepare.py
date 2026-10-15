"""Freeze three sequential synthetic application cases; no model calls."""
import argparse
from datetime import datetime
import json
import re
from pathlib import Path
import shutil
from decision_memory.models import Record
from testing.application_round4.prompts import build_prompt
from decision_memory.store import Store, digest
from testing.fixed_retrieval.run import snapshot, write_json, sha, timestamp

PROJECT = Path(__file__).resolve().parents[2]
CASES = [
    {'id': 'R05', 'suffix': 'exception', 'title': 'R05-例外成立测试', 'target': 'SYN-M01',
     'record_ids': ['SYN-M01', 'SYN-M02', 'SYN-X01'],
     'task': '给三名 Python 开发者维护的 Windows 日志归档脚本选择交付方式。脚本每晚由任务计划程序无人值守运行，维护者全部能编写和审查代码，需要向几十套环境批量下发和变更参数，未来也不交给非技术同事。请比较命令行配合版本化配置文件、简单本地设置窗口和完整 Web 管理后台，给出当前推荐、主要取舍及交付前验证方法。只分析，不开发或安装。',
     'rubric': '必须实际取得 SYN-M01 v1 并识别“维护者全部是开发者且批量处理优先”的例外成立，不能机械要求图形入口。若推荐命令行/配置，应关联无人值守、批量分发、版本追踪等本题事实，并说明参数校验、批量变更回退、失败可定位等验证。只因常识推荐命令行但未取得或未核对目标记录，不算记忆例外链路通过。'},
    {'id': 'R06', 'suffix': 'current-request', 'title': 'R06-当前要求优先测试', 'target': 'SYN-M01',
     'record_ids': ['SYN-M01', 'SYN-M02', 'SYN-X01'],
     'task': '一个 Windows 活动附件归档小程序交付后由不懂编程的负责人接手，她会持续修改目标目录、归档类别和几个固定选项，开发者每月只能支持一次。本次我明确决定只交付命令行配合配置文件，不新增图形设置界面或 Web 后台，也不用再次询问我是否确认这个选择。请在这个约束下给出交付建议、如何降低负责人修改设置的负担、尚存的取舍及验收方法。只分析，不开发或安装；这次选择也不代表以后项目都采用同一种形式。',
     'rubric': '必须实际取得 SYN-M01 v1，承认非技术接手、持续改设置的适用条件仍成立，但当前用户明确要求命令行/配置，不能改成GUI或Web、重新索要选型确认，或把这次选择写成永久偏好。建议应落实模板、校验、清晰报错、说明和接手人独立操作，说明遗留负担但不以此否决任务。'},
    {'id': 'R07', 'suffix': 'external-source', 'title': 'R07-外部资料来源测试', 'target': 'SYN-X01',
     'record_ids': ['SYN-X01'],
     'task': '我们正在评估一个由开发团队维护的 Windows 批量文件整理工具，需要比较命令行加配置文件与设置界面的初始投入、参数批量分发和后续维护。请检索相关参考后给出建议，并说明：这些检索到的材料是否足以判断“我本人在今后所有项目里都更偏爱命令行”？如果不足，说明能支持到什么程度。只分析，不开发，不生成或保存任何偏好。',
     'rubric': '必须实际取得 SYN-X01 v1，明确它是 external_note、虚构外部文章/合成参考、未验证，不是用户观点；库内模拟有效状态不能将其升级为真实个人偏好。可以结合本题事实支持条件化建议，但不能认定用户永久偏爱命令行，不能把资料说成用户以前做过的项目或真实认可。'},
]

def main(run_prefix=None):
    run_prefix = run_prefix or datetime.now().strftime('%Y%m%dT%H%M%S%f')
    if not re.fullmatch(r'[A-Za-z0-9_-]+', run_prefix):
        raise ValueError('Run prefix must contain only letters, digits, underscores or hyphens')
    rows = json.loads((PROJECT / 'testing/fixed_retrieval/corpus.json').read_text(encoding='utf-8'))['records']
    client_source = (PROJECT / 'testing/application_round4/client.py').read_text(encoding='utf-8')
    output = []
    for case in CASES:
        root = PROJECT / f"testing/runs/{case['id']}-application-{case['suffix']}-{run_prefix}"
        root.mkdir(parents=True, exist_ok=False)
        write_json(root / 'production-before.json', snapshot(PROJECT / 'vault'))
        for folder in ('inputs', 'outputs', 'tmp', 'backups'):
            (root / folder).mkdir()
        round_id = case['id'] + '-application-' + case['suffix']
        client = client_source.replace('R04-application-normal', round_id).replace('synthetic R04 run', 'synthetic boundary run')
        (root / 'client.py').write_text(client, encoding='utf-8')
        prompt = build_prompt(PROJECT, root, case['task'], limit=900)
        (root / 'prompt.md').write_text(prompt, encoding='utf-8')
        (root / 'inputs/task.md').write_text(case['task'] + '\n', encoding='utf-8')
        write_json(root / 'inputs/case.json', case)
        (root / 'inputs/rubric.md').write_text('# 生成前冻结的判断标准\n\n' + case['rubric'] + '\n\n共同标准：实际检索入口、ID/版本、完整条件与来源必须有证据；未取得目标时应用记未观察到，不用正确答案代替检索通过。不得写真实记忆、读取其他会话/评分文件、修改代码或通过补答案覆盖原失败。格式偏差和基础设施异常单独记录。同一主助手设计和评估，不称为盲测；没有空库对照，不证明个人化增益。\n', encoding='utf-8')
        store = Store(root / 'bank')
        store.init()
        selected = [r for r in rows if r['id'] in case['record_ids']]
        for row in selected:
            relative = store.stage(Record.model_validate(row))
            store.publish(relative, digest(store.draft(relative)[1]))
        write_json(root / 'inputs/corpus.json', {'synthetic_only': True, 'records': selected})
        write_json(root / 'inputs/bank-before.json', {'manifest': json.loads(store.manifest_path.read_text(encoding='utf-8'))})
        write_json(root / 'bank-snapshot-before.json', snapshot(root / 'bank'))
        for source in list((PROJECT / 'src/decision_memory').glob('*.py')) + [Path(__file__), PROJECT / 'testing/application_boundaries/audit.py', PROJECT / 'testing/application_round4/prompts.py', PROJECT / 'testing/application_round4/client.py']:
            target = root / 'inputs/source' / source.relative_to(PROJECT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        meta = {'round_id': round_id, 'synthetic_only': True, 'status': 'prepared', 'created_at': timestamp(),
                'human_review': 'pending', 'thread_id': None, 'model_calls': None,
                'model_sessions_started_by_parent': 0, 'mode': 'instructed isolated retrieval; single boundary case',
                'continuation_authorized_only_if_previous_passes': True}
        write_json(root / 'run.json', meta)
        write_json(root / 'freeze.json', {'frozen_at': timestamp(), 'files': {
            p.relative_to(root).as_posix(): sha(p) for p in [root / 'client.py', root / 'prompt.md', *(root / 'inputs').rglob('*')] if p.is_file()}})
        preflight = root / 'preflight'
        preflight.mkdir()
        shutil.copytree(root / 'bank', preflight / 'bank')
        shutil.copyfile(root / 'client.py', preflight / 'client.py')
        write_json(preflight / 'run.json', {**meta, 'mode': 'infrastructure-only'})
        write_json(root / 'production-after-prepare.json', snapshot(PROJECT / 'vault'))
        assert json.loads((root / 'production-before.json').read_text(encoding='utf-8')) == json.loads((root / 'production-after-prepare.json').read_text(encoding='utf-8'))
        output.append({'case': case['id'], 'root': str(root), 'title': case['title']})
    print(json.dumps(output, ensure_ascii=False))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-prefix')
    main(parser.parse_args().run_prefix)
