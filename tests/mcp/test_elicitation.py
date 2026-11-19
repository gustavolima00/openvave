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
