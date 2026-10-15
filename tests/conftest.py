import pytest

from decision_memory.models import Record
from decision_memory.store import Store


@pytest.fixture
def store(tmp_path):
    result = Store(tmp_path / "个人样例库")
    result.init()
    return result


@pytest.fixture
def record():
    return Record(id="DEMO-maintenance", title="演示案例：小项目先比较维护成本",
        kind="decision_case", tags=["维护成本", "选型"], aliases=["长期维护"],
        sources=["合成测试证据，不代表用户个人偏好"],
        considerations=["运维时间", "系统复杂度"], rationale="在演示的小规模情况下，先评估维护负担。",
        applies_when=["小规模演示项目", "维护人员较少"],
        exceptions=["存在高并发硬要求时不能直接沿用"], action="比较备份、升级与迁移工作量。",
        body="这是合成数据，不进入真实个人库。")
