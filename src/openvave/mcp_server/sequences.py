"""Persistent write tools (spec 006 US5, contracts/tools.md): ``preset_save`` and
``preset_restore``.

Both take the CLI's opt-ins unchanged (``unsafe`` is always required by the library), write the
library's automatic backup into the server's backup folder before the first write, and return the
CLI's ``sequence-result`` document plus ``summary`` and ``reminder``. With ``unsafe`` and no
``dry_run``, a client that declared elicitation is asked first (research R9); a client without it
is not asked (CLI parity).
"""

# No ``from __future__ import annotations`` here: the SDK reads the ``Resolve(...)`` markers of
# the tool parameters with ``typing.get_type_hints``, which cannot see the closure resolvers
# below in string annotations.

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from mcp.server.mcpserver import (
    AcceptedElicitation,
    Context,
    Elicit,
    ElicitationResult,
    MCPServer,
    Resolve,
)
from pydantic import BaseModel, Field

from openvave.cli import files, render
from openvave.errors import OpenvaveError
from openvave.mcp_server import backups
from openvave.mcp_server.errors import Declined, InvalidFile, InvalidValue, tool_errors
from openvave.mcp_server.holder import PedalHolder
from openvave.mcp_server.writes import DRY_RUN_REMINDER, parse_preset_position
from openvave.models import Backup, SequencePlan, SequenceResult
from openvave.protocol.storage import position as position_of
from openvave.session import OnBackup, TankG

DECLINED = "the owner did not confirm; nothing was read from or sent to the pedal"


class Confirm(BaseModel):
    """What the owner is asked (schema ``{confirm: boolean}``)."""

    confirm: bool = Field(description="true to go ahead and overwrite the stored preset(s)")


class _NotAsked:
    """The resolver's answer when nobody is asked (no elicitation, no ``unsafe``, ``dry_run``,
    or arguments the tool body refuses anyway)."""

    def __repr__(self) -> str:
        return "NOT_ASKED"


NOT_ASKED = _NotAsked()


def can_elicit(ctx: Context) -> bool:
    """Whether the client declared form elicitation (a bare ``elicitation: {}`` counts)."""
    capabilities = ctx.client_capabilities
    elicitation = capabilities.elicitation if capabilities is not None else None
    return elicitation is not None and (elicitation.form is not None or elicitation.url is None)


def proceeds(outcome: ElicitationResult[Confirm]) -> bool:
    """Not asked, or accepted with ``confirm: true``."""
    if not isinstance(outcome, AcceptedElicitation):
        return False  # declined or cancelled
    data: Any = outcome.data
    return data is NOT_ASKED or (isinstance(data, Confirm) and data.confirm)


def load_named_backup(folder: Path, name: str) -> Backup:
    """The backup file ``name`` in ``folder``, checked as the CLI checks a restore file;
    :class:`InvalidFile` otherwise (nothing connected yet)."""
    from openvave.cli import UsageError, load_restore_file

    path = backups.resolve_backup_file(folder, name)
    try:
        return load_restore_file(path)
    except UsageError as err:
        raise InvalidFile(str(err).replace(str(path), name)) from None


def restore_target(slot: str | int | None, everything: bool) -> int | None:
    """``slot`` xor ``all`` → the slot index (``None`` for all); :class:`InvalidValue`."""
    if (slot is None) == (not everything):
        raise InvalidValue(
            "give either slot (1A-9D or 0-35) or all: true" + (", not both" if everything else "")
        )
    return None if slot is None else parse_preset_position(slot, "slot")


def _summary(plan: SequencePlan, result: SequenceResult | None, source: str | None) -> str:
    if result is not None and not result.steps:
        return render.human_sequence_no_change(plan, source)
    head = render.human_sequence_header(plan, source).splitlines()[0]
    summary = " ".join(head.split("   UNSAFE")[0].split())
    if plan.action == "restore_all":
        summary += f" ({len(plan.changed_slots)} of 36 differ)"
    if result is None:
        if plan.refusal is not None:
            summary += f"; refused: {plan.refusal}"
        return summary + "; dry run: nothing sent, no backup taken"
    done = "saved" if plan.action == "save" else "restored"
    return f"{summary}; {done} and verified"


def register_sequences(
    server: MCPServer,
    holder: PedalHolder,
    annotations: Callable[[str], Any],
    record: Callable[[str], None],
) -> None:
    """Add ``preset_save`` and ``preset_restore`` to ``server``."""
    folder_text = str(holder.options.backup_dir)

    def ask_save(
        ctx: Context, to: str | int | None, unsafe: bool, dry_run: bool
    ) -> Elicit[Confirm] | _NotAsked:
        if not unsafe or dry_run or not can_elicit(ctx):
            return NOT_ASKED
        try:
            target = (
                "the loaded stored preset" if to is None else position_of(parse_preset_position(to))
            )
        except InvalidValue:
            return NOT_ASKED  # the tool body refuses it
        return Elicit(
            f"Overwrite stored preset {target} with the current sound? "
            f"A full backup is written to {folder_text} first.",
            Confirm,
        )

    def ask_restore(
        ctx: Context,
        file: str,
        slot: str | int | None,
        all: bool,  # noqa: A002 - the tool argument's name
        unsafe: bool,
        dry_run: bool,
    ) -> Elicit[Confirm] | _NotAsked:
        if not unsafe or dry_run or not can_elicit(ctx):
            return NOT_ASKED
        try:
            index = restore_target(slot, all)
            load_named_backup(holder.options.backup_dir, file)
        except ValueError:
            return NOT_ASKED  # the tool body refuses it
        what = "all 36 stored presets" if index is None else f"stored preset {position_of(index)}"
        return Elicit(
            f"Overwrite {what} with the backup file {file}? "
            f"A full backup is written to {folder_text} first.",
            Confirm,
        )

    async def sequence(
        command: str,
        dry_run: bool,
        plan_call: Callable[[TankG], Awaitable[SequencePlan]],
        run_call: Callable[[TankG, OnBackup], Awaitable[SequenceResult]],
        source: str | None,
    ) -> dict[str, Any]:
        """Plan (``dry_run``) or run one save / restore: the CLI's ``sequence_json`` document."""
        action = "save" if command == "preset save" else "restore"
        held: dict[str, TankG] = {}
        saved: list[Path] = []

        def on_backup(backup: Backup) -> None:
            folder = backups.ensure_dir(holder.options.backup_dir)
            document = backup.to_document()
            while True:
                path = files.automatic_backup_path(folder, action, datetime.now())
                try:
                    files.write_json_atomic(path, document, force=False)
                except files.TargetExistsError:
                    continue  # taken between the check and the write: next name
                except OSError as err:
                    raise InvalidFile(
                        f"cannot write the automatic backup to {folder}: "
                        f"{err.strerror or err}; nothing was written to the pedal"
                    ) from None
                break
            saved.append(path)

        def document(plan: SequencePlan, result: SequenceResult | None) -> dict[str, Any]:
            pedal = held["pedal"]
            return render.sequence_json(
                command,
                plan,
                result,
                dry_run=result is None,
                read_at=datetime.now(UTC),
                device=pedal.device,
                identity=pedal.identity,
                source=source,
                backup_saved_to=str(saved[0]) if saved else None,
            )

        def partial(err: OpenvaveError) -> dict[str, Any] | None:
            if err.sequence is None or not held:
                return None
            return document(err.sequence.plan, err.sequence)

        def notes(err: OpenvaveError) -> list[str]:
            lines = []
            if err.sequence is not None and err.sequence.stored_may_have_changed:
                lines.append("stored presets may have changed; nothing was retried")
            if saved:
                name = saved[0].name
                lines.append(
                    f"backup: {saved[0]} (taken before the first write; check with "
                    f"preset_backup, undo with preset_restore file={name} all=true unsafe=true)"
                )
            return lines

        with tool_errors(record, partial, notes):
            async with holder.use() as pedal:
                held["pedal"] = pedal
                result: SequenceResult | None
                if dry_run:
                    plan, result = await plan_call(pedal), None
                else:
                    result = await run_call(pedal, on_backup)
                    plan = result.plan
                body = document(plan, result)
        if dry_run:
            reminder = DRY_RUN_REMINDER
        elif saved:
            reminder = f"automatic backup: {saved[0]} (taken before the first write)"
        else:
            reminder = "nothing sent; no backup taken"
        return {"summary": _summary(plan, result, source), **body, "reminder": reminder}

    @server.tool(annotations=annotations("preset_save"))
    async def preset_save(
        confirmation: Annotated[ElicitationResult[Confirm], Resolve(ask_save)],
        to: str | int | None = None,
        dry_run: bool = False,
        unsafe: bool = False,
        experimental: bool = False,
    ) -> dict[str, Any]:
        """Store the current sound (edit buffer) in a stored preset: the loaded one, or to
        (1A-9D or 0-35). PERSISTENT: overwrites that stored preset. Needs unsafe: true (ask the
        owner first; the owner may also be asked directly). Normal mode only. A full backup of
        all 36 presets is written to the backup folder first; its name is in the result and
        preset_restore can put it back. Nothing to change: nothing sent, no backup. dry_run:
        plan only, every step and frame shown, nothing sent. experimental: allow untested
        firmware."""
        with tool_errors(record):
            index = None if to is None else parse_preset_position(to, "to")
            if not proceeds(confirmation):
                raise Declined(DECLINED)
        return await sequence(
            "preset save",
            dry_run,
            lambda p: p.plan_save(index, unsafe=unsafe, experimental=experimental),
            lambda p, on_backup: p.save_preset(
                index, unsafe=unsafe, experimental=experimental, on_backup=on_backup
            ),
            None,
        )

    @server.tool(annotations=annotations("preset_restore"))
    async def preset_restore(
        confirmation: Annotated[ElicitationResult[Confirm], Resolve(ask_restore)],
        file: str,
        slot: str | int | None = None,
        all: bool = False,  # noqa: A002 - the contract's argument name
        dry_run: bool = False,
        unsafe: bool = False,
        discard_edits: bool = False,
        experimental: bool = False,
    ) -> dict[str, Any]:
        """Restore stored presets from a backup file in the backup folder (file: a name listed
        by backups_list, not a path): slot (1A-9D or 0-35) restores one preset, all: true
        writes all 36 and selects the preset that was loaded. PERSISTENT: overwrites stored
        presets. Needs unsafe: true (ask the owner first; the owner may also be asked
        directly). A full backup is written to the backup folder first. Unsaved edits to the
        current sound need discard_edits (the final select discards them); a file from another
        firmware needs experimental. dry_run: plan only, nothing sent."""
        with tool_errors(record):
            index = restore_target(slot, all)
            backup = load_named_backup(holder.options.backup_dir, file)
            if not proceeds(confirmation):
                raise Declined(DECLINED)
        everything = all
        return await sequence(
            "preset restore",
            dry_run,
            lambda p: p.plan_restore(
                backup,
                slot=index,
                all=everything,
                unsafe=unsafe,
                experimental=experimental,
                discard_edits=discard_edits,
            ),
            lambda p, on_backup: p.restore(
                backup,
                slot=index,
                all=everything,
                unsafe=unsafe,
                experimental=experimental,
                discard_edits=discard_edits,
                on_backup=on_backup,
            ),
            file,
        )


__all__ = [
    "NOT_ASKED",
    "Confirm",
    "can_elicit",
    "load_named_backup",
    "proceeds",
    "register_sequences",
    "restore_target",
]
