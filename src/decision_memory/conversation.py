"""Conversation approval helpers. User intent is checked by the agent, not this CLI."""

from .models import parse_record, render_record
from .store import MemoryError, Store, digest


def preview(store: Store, source: str, stdin: bytes | None = None) -> dict:
    """Return the entire version for display, without writing a candidate or index."""
    if source == "-":
        record = parse_record(stdin or b"")
        raw = render_record(record)
        relative = f"drafts/{record.id}.md"
    else:
        record, raw = store.draft(source)
        relative = source
    manifest = store._manifest()
    previous = manifest["entries"].get(record.id)
    version = previous["version"] if previous else 0
    sha256 = digest(raw)
    already_active = bool(previous and previous["status"] == "active" and previous["sha256"] == sha256)
    if not already_active and record.base_version != version:
        raise MemoryError(f"正式版本已经变化：当前为 {version}，请先更新候选再展示审核")
    return {"id": record.id, "version": version if already_active else version + 1,
            "base_version": record.base_version, "draft": relative,
            "vault_id": manifest["vault_id"], "sha256": sha256,
            "content": raw.decode("utf-8"), "already_active": already_active,
            "notice": "必须展示完整内容；批准须来自当前用户。内容指纹不能证明用户本人授权。"}


def confirmation(confirmed: bool, message: str) -> dict:
    if not confirmed or not message.strip():
        raise MemoryError("需要用户明确批准此版本后，提供 --confirmed 和用户确认原话")
    return {"channel": "conversation", "user_confirmation": message.strip(),
            "evidence": "agent-transcribed; not independently authenticated"}


def approve(store: Store, relative: str, sha256: str, vault_id: str,
            confirmed: bool, message: str) -> dict:
    evidence = confirmation(confirmed, message)
    result = store.publish(relative, sha256, expected_vault_id=vault_id, approval=evidence)
    return {**result, "sha256": sha256, "approval_channel": "conversation"}


def revoke(store: Store, record_id: str, sha256: str, vault_id: str,
           confirmed: bool, message: str) -> dict:
    evidence = confirmation(confirmed, message)
    return store.revoke(record_id, sha256, expected_vault_id=vault_id, approval=evidence)
