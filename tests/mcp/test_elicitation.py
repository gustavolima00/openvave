"""The owner's confirmation before ``preset_save`` / ``preset_restore`` (spec 006 research R9,
contracts/tools.md §Elicitation), in both the legacy and the modern protocol modes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from mcp import types

from tests.mcp.conftest import CountingFactory, open_harness, options
from tests.support import restore_fixture as rf
from tests.support import storage_fixture as sf
from tests.support.write_fixture import NORMAL, make_fake, writes

pytestmark = pytest.mark.persistent_writes

P = sf.PUBLIC_PRESET
GAIN_90 = P[:6] + bytes([90]) + P[7:]
MODES = ["legacy", "auto"]


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("openvave.session.SEQUENCE_SLEEP", no_sleep)
    monkeypatch.setattr("openvave.session.SELECT_SLEEP", no_sleep)
    monkeypatch.setattr("openvave.session.STATE_SLEEP", no_sleep)


def edited_fake() -> Any:
    presets = sf.synthetic_presets()
    presets[2] = P
    return make_fake(NORMAL, buffer=GAIN_90, image=sf.HEADER + b"".join(presets))


def changed_fake() -> Any:
    return make_fake(NORMAL, image=rf.image_with(s2=GAIN_90, s9=GAIN_90, s35=GAIN_90))


class Owner:
    """An elicitation callback answering with ``action`` (and ``confirm``), recording messages."""

    def __init__(self, action: str, confirm: bool | None = True) -> None:
        self.action = action
        self.confirm = confirm
        self.messages: list[str] = []
        self.schemas: list[dict[str, Any]] = []

    async def __call__(self, context: Any, params: types.ElicitRequestParams) -> types.ElicitResult:
        self.messages.append(params.message)
        self.schemas.append(getattr(params, "requested_schema", {}) or {})
        content = None
        if self.action == "accept":
            content = {"confirm": self.confirm} if self.confirm is not None else {}
        return types.ElicitResult(action=self.action, content=content)  # type: ignore[arg-type]


def backups(tmp_path: Path) -> list[Path]:
    folder = tmp_path / "backups"
    return sorted(folder.glob("tankg-backup-*-before-*.json")) if folder.exists() else []


@pytest.mark.parametrize("mode", MODES)
async def test_accept_with_confirm_runs_the_save(tmp_path, mode) -> None:
    owner = Owner("accept", True)
    factory = CountingFactory(make=edited_fake)
    async with open_harness(options(tmp_path), factory, mode=mode, elicitation_callback=owner) as h:
        result = await h.ok("preset_save", {"to": "1C", "unsafe": True})
    assert len(owner.messages) == 1
    message = owner.messages[0]
    assert "1C" in message and str(tmp_path / "backups") in message
    assert set(owner.schemas[0].get("properties", {})) == {"confirm"}
    assert len(writes(factory.fake)) == 3
    assert result["backup_saved_to"] is not None
    assert len(backups(tmp_path)) == 1


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize(
    ("action", "confirm"),
    [("decline", None), ("cancel", None), ("accept", False)],
    ids=["decline", "cancel", "confirm_false"],
)
async def test_anything_but_confirm_sends_nothing(tmp_path, mode, action, confirm) -> None:
    owner = Owner(action, confirm)
    factory = CountingFactory(make=edited_fake)
    async with open_harness(options(tmp_path), factory, mode=mode, elicitation_callback=owner) as h:
        text = await h.error("preset_save", {"to": "1C", "unsafe": True})
        status = await h.ok("pedal_status")
    assert text.startswith("declined_by_owner: ")
    assert len(owner.messages) == 1
    assert factory.calls == 0  # asked before connecting: nothing read or sent
    assert backups(tmp_path) == []
    assert status["last_error"].startswith("declined_by_owner")


@pytest.mark.parametrize("mode", MODES)
async def test_restore_message_names_the_file_and_the_slots(tmp_path, mode) -> None:
    folder = tmp_path / "backups"
    folder.mkdir()
    (folder / "source.json").write_text(json.dumps(rf.document()), encoding="utf-8")
    owner = Owner("accept", True)
    factory = CountingFactory(make=changed_fake)
    async with open_harness(options(tmp_path), factory, mode=mode, elicitation_callback=owner) as h:
        await h.ok("preset_restore", {"file": "source.json", "all": True, "unsafe": True})
        await h.ok("preset_restore", {"file": "source.json", "slot": "3B", "unsafe": True})
    assert len(owner.messages) == 2
    everything, one = owner.messages
    assert "source.json" in everything and "all 36" in everything
    assert "3B" in one and "source.json" in one
    assert str(folder) in everything and str(folder) in one


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize(
    "args",
    [{"to": "1C"}, {"to": "1C", "unsafe": True, "dry_run": True}],
    ids=["without_unsafe", "dry_run"],
)
async def test_not_asked_without_unsafe_or_with_dry_run(tmp_path, mode, args) -> None:
    owner = Owner("accept", True)
    factory = CountingFactory(make=edited_fake)
    async with open_harness(options(tmp_path), factory, mode=mode, elicitation_callback=owner) as h:
        await h.call("preset_save", args)
    assert owner.messages == []
    assert writes(factory.fake) == []


@pytest.mark.parametrize("mode", MODES)
async def test_not_asked_when_the_arguments_are_invalid(tmp_path, mode) -> None:
    owner = Owner("accept", True)
    factory = CountingFactory(make=changed_fake)
    async with open_harness(options(tmp_path), factory, mode=mode, elicitation_callback=owner) as h:
        save = await h.error("preset_save", {"to": "10A", "unsafe": True})
        restore = await h.error(
            "preset_restore", {"file": "../x.json", "all": True, "unsafe": True}
        )
    assert save.startswith("invalid_value: ") and restore.startswith("invalid_file: ")
    assert owner.messages == []
    assert factory.calls == 0


@pytest.mark.parametrize("mode", MODES)
async def test_client_without_elicitation_is_not_asked(tmp_path, mode) -> None:
    factory = CountingFactory(make=edited_fake)
    async with open_harness(options(tmp_path), factory, mode=mode) as h:
        result = await h.ok("preset_save", {"to": "1C", "unsafe": True})
    assert len(writes(factory.fake)) == 3
    assert result["backup_saved_to"] is not None


async def test_the_confirmation_is_not_a_tool_argument(tmp_path) -> None:
    async with open_harness(options(tmp_path), CountingFactory()) as h:
        listed = {t.name: t for t in (await h.client.list_tools()).tools}
    assert set(listed["preset_save"].input_schema["properties"]) == {
        "to",
        "dry_run",
        "unsafe",
        "experimental",
    }
    restore = listed["preset_restore"].input_schema
    assert "confirmation" not in restore["properties"]
    assert restore.get("required") == ["file"]


class ReplacingOwner(Owner):
    """Accepts, but the first time it is asked the restore file is replaced by another valid
    backup while the question is open (spec 006 T064, Codex review of 0475c9e [P1])."""

    def __init__(self, path: Path, replacement: dict[str, Any]) -> None:
        super().__init__("accept", True)
        self.path = path
        self.replacement = replacement

    async def __call__(self, context: Any, params: types.ElicitRequestParams) -> types.ElicitResult:
        if not self.messages:
            self.path.write_text(json.dumps(self.replacement), encoding="utf-8")
        return await super().__call__(context, params)


def preset_document(data: bytes) -> dict[str, Any]:
    from datetime import UTC, datetime

    from openvave import PresetFile

    return PresetFile(
        identity=rf.identity(),
        created_at=datetime(2026, 11, 19, 12, 0, tzinfo=UTC),
        source_index=4,
        data=data,
    ).to_document()


def fingerprint(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()[:12]


@pytest.mark.parametrize("mode", MODES)
async def test_restore_writes_the_backup_the_owner_was_asked_about(tmp_path, mode) -> None:
    from openvave import Backup

    folder = tmp_path / "backups"
    folder.mkdir()
    source = folder / "source.json"
    first = rf.document()
    source.write_text(json.dumps(first), encoding="utf-8")
    first_bytes = source.read_bytes()
    second = rf.document(rf.image_with(s5=GAIN_90))
    owner = ReplacingOwner(source, second)
    factory = CountingFactory(make=changed_fake)
    async with open_harness(options(tmp_path), factory, mode=mode, elicitation_callback=owner) as h:
        await h.ok("preset_restore", {"file": "source.json", "all": True, "unsafe": True})
        after = await h.ok("preset_backup")
    stored = Backup.from_document(json.loads(Path(after["path"]).read_text(encoding="utf-8")))
    assert f"(fingerprint {fingerprint(first_bytes)})" in owner.messages[0]
    if len(owner.messages) == 1:
        # Asked once (legacy: the question is sent mid-call): the snapshot that was asked about
        # is written, not the file that replaced it.
        assert stored.image == Backup.from_document(first).image
    else:
        # Asked again (modern mode re-reads the file on the retry): the new question names the
        # new bytes, and only what the owner accepted last is written.
        assert len(owner.messages) == 2
        assert f"(fingerprint {fingerprint(source.read_bytes())})" in owner.messages[1]
        assert stored.image == Backup.from_document(second).image


@pytest.mark.parametrize("mode", MODES)
async def test_import_writes_the_preset_file_the_owner_was_asked_about(tmp_path, mode) -> None:
    from openvave import Backup

    folder = tmp_path / "backups"
    folder.mkdir()
    source = folder / "tone.json"
    first = preset_document(GAIN_90)
    source.write_text(json.dumps(first), encoding="utf-8")
    first_bytes = source.read_bytes()
    other = P[:7] + bytes([33]) + P[8:]
    second = preset_document(other)
    owner = ReplacingOwner(source, second)
    factory = CountingFactory(make=changed_fake)
    async with open_harness(options(tmp_path), factory, mode=mode, elicitation_callback=owner) as h:
        await h.ok("preset_import", {"file": "tone.json", "to": "2C", "unsafe": True})
        after = await h.ok("preset_backup")
    stored = Backup.from_document(json.loads(Path(after["path"]).read_text(encoding="utf-8")))
    slot = stored.image[2 + 21 * 6 : 23 + 21 * 6]
    assert f"(fingerprint {fingerprint(first_bytes)})" in owner.messages[0]
    assert slot == (GAIN_90 if len(owner.messages) == 1 else other)


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("preset_restore", {"file": "source.json", "slot": "10A"}),
        ("preset_restore", {"file": "source.json", "slot": "1A", "all": True}),
        ("preset_restore", {"file": "source.json"}),
        ("preset_import", {"file": "source.json", "to": "10A"}),
    ],
    ids=["bad_slot", "slot_and_all", "neither", "bad_to"],
)
async def test_bad_destination_is_refused_without_reading_the_file(
    tmp_path, monkeypatch, tool, args
) -> None:
    """Codex round 2 [P3]: a refusal that depends only on the arguments opens no file."""
    folder = tmp_path / "backups"
    folder.mkdir()
    (folder / "source.json").write_text(json.dumps(rf.document()), encoding="utf-8")
    read: list[str] = []
    real = Path.read_bytes

    def counting(self: Path) -> bytes:
        read.append(self.name)
        return real(self)

    monkeypatch.setattr(Path, "read_bytes", counting)
    owner = Owner("accept", True)
    async with open_harness(options(tmp_path), CountingFactory(), elicitation_callback=owner) as h:
        text = await h.error(tool, {**args, "unsafe": True})
    assert text.startswith("invalid_value: ")
    assert read == [] and owner.messages == []
