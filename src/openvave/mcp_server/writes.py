"""Volatile write tools (spec 006 US2, contracts/tools.md): ``pedal_set``, ``preset_select``,
``preset_reload``, ``bypass_on``, ``bypass_off`` and ``loopback``.

Each tool parses its arguments as the CLI does before connecting, then calls the library's
``plan_*`` (``dry_run``) or write method with the opt-ins unchanged, and returns the CLI's
``--json`` document for the same command plus ``summary`` and ``reminder``. A refusal, NAK or
lost link is a tool error; a write that stopped midway carries the CLI's document so far as
``partial``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from mcp.server.mcpserver import MCPServer

from openvave.cli import UsageError, parse_assignments, render
from openvave.errors import OpenvaveError, WriteNotAppliedError
from openvave.mcp_server.errors import InvalidValue, UnknownField, tool_errors
from openvave.mcp_server.holder import PedalHolder
from openvave.models import EditPlan, EditResult, WritePlan, WriteResult
from openvave.protocol.storage import parse_position
from openvave.protocol.storage import position as position_of
from openvave.protocol.writes import WRITABLE_FIELDS
from openvave.session import FieldValue, TankG

ToolAnnotationsOf = Callable[[str], Any]
FieldInput = str | int | float | bool

DRY_RUN_REMINDER = "dry run: nothing sent"
NOT_SAVED = "not saved; discard with preset_reload"
NOT_SAVED_EDIT = "not saved; discard with preset_reload and discard_edits: true"
PRESETS_UNCHANGED = "nothing saved; the stored presets are unchanged"
LOOPBACK_REMINDER = "a volatile setting; nothing saved to the presets"
EDIT_MODE = 0


def changes_to_pairs(changes: dict[str, FieldInput]) -> list[tuple[str, FieldValue]]:
    """``pedal_set.changes`` → the CLI's parsed ``FIELD=VALUE`` pairs (nothing read or sent).

    JSON numbers and booleans become the CLI's text (``90``, ``on`` / ``off``); the text then
    goes through :func:`openvave.cli.parse_assignments`. Raises :class:`UnknownField` and
    :class:`InvalidValue`."""
    if not changes:
        raise InvalidValue(
            'changes is empty: give at least one field and its value, e.g. {"gain": 90} '
            "(writable fields: resource openvave://fields)"
        )
    unknown = [name for name in changes if name not in WRITABLE_FIELDS]
    if unknown:
        raise UnknownField(
            f"unknown field {unknown[0]!r}; writable fields: {', '.join(WRITABLE_FIELDS)} "
            "(details: resource openvave://fields)"
        )
    texts = [f"{name}={_value_text(name, value)}" for name, value in changes.items()]
    try:
        parsed = parse_assignments(texts, None, False)
    except UsageError as err:
        raise InvalidValue(str(err)) from None
    assert isinstance(parsed, list)  # every text is FIELD=VALUE
    return parsed


def _value_text(name: str, value: FieldInput) -> str:
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        raise InvalidValue(f"{name} takes a whole number, got {value:g}")
    text = value.strip()
    if not text:
        raise InvalidValue(f"{name}: empty value")
    return text


def parse_preset_position(value: str | int, argument: str = "position") -> int:
    """``"2C"`` / ``"2c"`` / ``"6"`` / ``6`` → 6; :class:`InvalidValue` otherwise."""
    try:
        return parse_position(str(value).strip())
    except ValueError as err:
        raise InvalidValue(f"{argument}: {err}") from None


def _summary(human: str, plan: WritePlan | EditPlan, dry_run: bool) -> str:
    first = next((line for line in human.splitlines() if line.strip()), "")
    summary = " ".join(first.split())
    if plan.no_change and plan.refusal is None:
        return summary
    if plan.refusal is not None:
        summary += f"; refused: {plan.refusal}"
    if dry_run:
        summary += "; dry run: nothing sent"
    return summary


HUMAN: dict[str, Callable[..., str]] = {
    "preset select": render.human_select,
    "preset reload": render.human_reload,
    "bypass on": render.human_bypass_on,
    "bypass off": render.human_bypass_off,
}


def register_writes(
    server: MCPServer,
    holder: PedalHolder,
    annotations: ToolAnnotationsOf,
    record: Callable[[str], None],
) -> None:
    """Add the six volatile write tools to ``server``."""

    async def write(
        command: str,
        dry_run: bool,
        plan_call: Callable[[TankG], Awaitable[WritePlan]],
        write_call: Callable[[TankG], Awaitable[WriteResult]],
    ) -> tuple[dict[str, Any], WritePlan, WriteResult | None]:
        """One single-frame write (or its plan): the CLI's ``write_json`` document."""
        held: dict[str, TankG] = {}

        def partial(err: OpenvaveError) -> dict[str, Any] | None:
            if not isinstance(err, WriteNotAppliedError) or err.result is None or not held:
                return None
            pedal = held["pedal"]
            return render.write_json(
                command,
                err.result.plan,
                err.result,
                dry_run=False,
                read_at=datetime.now(UTC),
                device=pedal.device,
                identity=pedal.identity,
            )

        with tool_errors(record, partial):
            async with holder.use() as pedal:
                held["pedal"] = pedal
                result: WriteResult | None
                if dry_run:
                    plan, result = await plan_call(pedal), None
                else:
                    result = await write_call(pedal)
                    plan = result.plan
                device, identity = pedal.device, pedal.identity
        document = render.write_json(
            command,
            plan,
            result,
            dry_run=dry_run,
            read_at=datetime.now(UTC),
            device=device,
            identity=identity,
        )
        human = (render.human_loopback if command.startswith("loopback") else HUMAN[command])(
            plan, result, dry_run=dry_run
        )
        document = {"summary": _summary(human, plan, dry_run), **document}
        return document, plan, result

    @server.tool(annotations=annotations("pedal_set"))
    async def pedal_set(
        changes: dict[str, FieldInput], dry_run: bool = False, experimental: bool = False
    ) -> dict[str, Any]:
        """Change fields of the current sound (edit buffer), all over one connection: changes
        maps field names to values, e.g. {"gain": 90, "delay_on": "on", "led_colour":
        "#2040ff", "reverb_decay": "room:18"} (syntax and ranges: resource openvave://fields;
        typed knobs take TYPE:POSITION, a position in the current type, or raw:N). Knobs share
        one message; each block switch and the LED colour get their own. NOT saved: the stored
        preset is unchanged, discard with preset_reload. Refused, with nothing sent, in tuner
        mode, while bypassed, or for a value out of range. dry_run: plan only, frames shown,
        nothing sent. experimental: also send messages not yet confirmed on hardware (block
        switches, LED colour) or on untested firmware; ask the owner first."""
        held: dict[str, TankG] = {}

        def edit_document(plan: EditPlan, result: EditResult | None) -> dict[str, Any]:
            pedal = held["pedal"]
            return render.edit_json(
                plan,
                result,
                dry_run=result is None,
                read_at=datetime.now(UTC),
                device=pedal.device,
                identity=pedal.identity,
            )

        def partial(err: OpenvaveError) -> dict[str, Any] | None:
            if err.edit is None or not held:
                return None
            return edit_document(err.edit.plan, err.edit)

        with tool_errors(record, partial):
            pairs = changes_to_pairs(changes)
            async with holder.use() as pedal:
                held["pedal"] = pedal
                result: EditResult | None
                if dry_run:
                    plan = await pedal.plan_set_fields(pairs, experimental=experimental)
                    result = None
                else:
                    result = await pedal.set_fields(pairs, experimental=experimental)
                    plan = result.plan
                document = edit_document(plan, result)
        summary = _summary(render.human_edit(plan, result), plan, dry_run)
        if dry_run:
            reminder = DRY_RUN_REMINDER
        elif plan.no_change:
            reminder = "nothing changed"
        else:
            edit_mode = plan.global_before.data[3] == EDIT_MODE
            reminder = NOT_SAVED_EDIT if edit_mode else NOT_SAVED
        return {"summary": summary, **document, "reminder": reminder}

    @server.tool(annotations=annotations("preset_select"))
    async def preset_select(
        position: str | int,
        dry_run: bool = False,
        discard_edits: bool = False,
        experimental: bool = False,
    ) -> dict[str, Any]:
        """Load stored preset position (1A-9D, or index 0-35) as the current sound. Stored
        presets are not changed. In edit mode the pedal's unsaved edits would be lost: refused
        unless discard_edits (ask the owner first). dry_run: plan only, nothing sent.
        experimental: allow untested firmware."""
        with tool_errors(record):
            index = parse_preset_position(position)
        document, _, result = await write(
            "preset select",
            dry_run,
            lambda p: p.plan_select(index, discard_edits=discard_edits, experimental=experimental),
            lambda p: p.select_preset(
                index, discard_edits=discard_edits, experimental=experimental
            ),
        )
        if result is not None:
            holder.bypass_return = None  # a loaded preset leaves bypass
        return {**document, "reminder": DRY_RUN_REMINDER if dry_run else PRESETS_UNCHANGED}

    @server.tool(annotations=annotations("preset_reload"))
    async def preset_reload(
        dry_run: bool = False, discard_edits: bool = False, experimental: bool = False
    ) -> dict[str, Any]:
        """Discard unsaved edits to the current sound by loading the current stored preset
        again (nothing to discard: nothing sent). In edit mode it needs discard_edits; refused
        in tuner mode and while bypassed. dry_run: plan only. experimental: allow untested
        firmware."""
        document, _, _ = await write(
            "preset reload",
            dry_run,
            lambda p: p.plan_reload(discard_edits=discard_edits, experimental=experimental),
            lambda p: p.reload_preset(discard_edits=discard_edits, experimental=experimental),
        )
        return {**document, "reminder": DRY_RUN_REMINDER if dry_run else PRESETS_UNCHANGED}

    @server.tool(annotations=annotations("bypass_on"))
    async def bypass_on(
        dry_run: bool = False, discard_edits: bool = False, experimental: bool = False
    ) -> dict[str, Any]:
        """Bypass the pedal (all blocks off). Normal mode only; unsaved edits to the current
        sound need discard_edits (they are lost). The result's return_position is the preset
        bypass_off goes back to; this server remembers it. dry_run: plan only. experimental:
        allow untested firmware."""
        document, plan, result = await write(
            "bypass on",
            dry_run,
            lambda p: p.plan_bypass_on(discard_edits=discard_edits, experimental=experimental),
            lambda p: p.bypass_on(discard_edits=discard_edits, experimental=experimental),
        )
        if result is not None and result.return_index is not None:
            holder.bypass_return = result.return_index
        if dry_run:
            reminder = DRY_RUN_REMINDER
        elif holder.bypass_return is not None:
            back = position_of(holder.bypass_return)
            reminder = f"bypassed; bypass_off returns to {back}"
        else:
            reminder = "bypassed; bypass_off needs a position (the pedal does not report it)"
        return {**document, "reminder": reminder}

    @server.tool(annotations=annotations("bypass_off"))
    async def bypass_off(
        position: str | int | None = None, dry_run: bool = False, experimental: bool = False
    ) -> dict[str, Any]:
        """Leave bypass by loading preset position (1A-9D or 0-35). Without position: the one
        bypass_on reported in this server session. Refused when the pedal is not bypassed (use
        preset_select). dry_run: plan only. experimental: allow untested firmware."""
        with tool_errors(record):
            if position is not None:
                index = parse_preset_position(position)
            elif holder.bypass_return is not None:
                index = holder.bypass_return
            else:
                async with holder.use() as pedal:
                    state = await pedal.state()
                raise InvalidValue(_position_missing(state))
        document, _, result = await write(
            "bypass off",
            dry_run,
            lambda p: p.plan_bypass_off(index, experimental=experimental),
            lambda p: p.bypass_off(index, experimental=experimental),
        )
        if result is not None:
            holder.bypass_return = None
        return {**document, "reminder": DRY_RUN_REMINDER if dry_run else PRESETS_UNCHANGED}

    @server.tool(annotations=annotations("loopback"))
    async def loopback(
        on: bool, dry_run: bool = False, experimental: bool = False
    ) -> dict[str, Any]:
        """Turn loopback on or off (Bluetooth audio mixed into the USB recording). The message
        is not yet confirmed on hardware, so it needs experimental (ask the owner first).
        Already set: nothing sent. dry_run: plan only."""
        state = "on" if on else "off"
        document, _, _ = await write(
            f"loopback {state}",
            dry_run,
            lambda p: p.plan_loopback(on, experimental=experimental),
            lambda p: p.set_loopback(on, experimental=experimental),
        )
        return {**document, "reminder": DRY_RUN_REMINDER if dry_run else LOOPBACK_REMINDER}


def _position_missing(state: Any) -> str:
    """``bypass_off`` without a position or a remembered one (the CLI's text, tool words)."""
    if state.kind == "bypass" and state.bank is not None:
        bank = state.bank + 1
        return (
            "a position is required: the pedal does not report the loaded slot while bypassed "
            f"(it reports bank {bank}); give position {bank}A … {bank}D"
        )
    where = f" (on {state.position})" if state.position else ""
    return (
        f"a position is required, and the pedal is not bypassed{where} ({state.label}); "
        "to load a preset use preset_select"
    )


__all__ = ["changes_to_pairs", "parse_preset_position", "register_writes"]
