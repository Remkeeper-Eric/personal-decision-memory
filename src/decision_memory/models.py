"""The schema describes user-authored meaning; approval lives outside the note."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
import yaml


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1] = 1
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
    title: str = Field(min_length=1, max_length=160)
    kind: Literal["preference", "decision_case", "lesson", "project_fact", "external_note"]
    base_version: int = Field(default=0, ge=0)
    project_scope: list[str] = Field(default_factory=list, max_length=30)
    environments: list[str] = Field(default_factory=list, max_length=30)
    tags: list[str] = Field(default_factory=list, max_length=40)
    aliases: list[str] = Field(default_factory=list, max_length=40)
    sources: list[str] = Field(min_length=1, max_length=30)
    considerations: list[str] = Field(min_length=1, max_length=30)
    rationale: str = Field(min_length=1, max_length=20000)
    applies_when: list[str] = Field(min_length=1, max_length=30)
    exceptions: list[str] = Field(default_factory=list, max_length=30)
    action: str = Field(min_length=1, max_length=12000)
    verification: Literal["unverified", "observed", "validated"] = "unverified"
    body: str = Field(default="", max_length=50000)

    @field_validator("project_scope", "environments", "tags", "aliases", "sources",
                     "considerations", "applies_when", "exceptions")
    @classmethod
    def clean_items(cls, items: list[str]) -> list[str]:
        if any(not x.strip() or len(x) > 2000 for x in items):
            raise ValueError("列表项必须非空，且每项不超过 2000 字符")
        return list(dict.fromkeys(x.strip() for x in items))


class UniqueSafeLoader(yaml.SafeLoader):
    pass


def _unique_mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str) or key in result:
            raise ValueError("YAML 属性名必须是唯一字符串")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueSafeLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


def parse_record(raw: bytes) -> Record:
    if len(raw) > 128 * 1024:
        raise ValueError("单条记录不能超过 128 KiB")
    text = raw.decode("utf-8-sig").replace("\r\n", "\n")
    if not text.startswith("---\n"):
        raise ValueError("记录需要以 YAML 属性块开始")
    split = text.find("\n---\n", 4)
    if split < 0:
        raise ValueError("YAML 属性块缺少结束分隔符")
    data = yaml.load(text[4:split], Loader=UniqueSafeLoader)
    if not isinstance(data, dict) or "body" in data:
        raise ValueError("正文应放在属性块之后")
    data["body"] = text[split + 5:].strip()
    return Record.model_validate(data)


def render_record(record: Record) -> bytes:
    data = record.model_dump(exclude={"body"})
    front = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    return f"---\n{front}---\n\n{record.body}\n".encode("utf-8")


def in_scope(record: Record, project: str, environments: list[str]) -> bool:
    return ((not record.project_scope or project in record.project_scope)
            and set(record.environments).issubset(environments))
