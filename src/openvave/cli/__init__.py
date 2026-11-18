"""``openvave`` command-line interface (contracts/cli.md).

Parses arguments, runs one session, renders the result. Results go to stdout; errors, warnings
and the hex trace go to stderr. Exit codes are part of the public contract.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import re
import sys
import traceback
from collections.abc import Awaitable, Callable, Coroutine, Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from openvave import __version__
from openvave.cli import files, render, watch
from openvave.errors import (
    BluetoothUnavailableError,
    MultipleDevicesError,
    OpenvaveError,
    WriteNotAppliedError,
)
from openvave.models import DeviceInfo, WritePlan, WriteResult
from openvave.protocol.bytemap import REVERB_SECTION_STEPS, TYPED_FIELDS
from openvave.protocol.storage import parse_position
from openvave.protocol.writes import WRITABLE_FIELDS
from openvave.session import DEFAULT_SCAN_TIMEOUT, DEFAULT_TIMEOUT, FieldValue, TankG
from openvave.transport import Transport

TransportFactory = Callable[[str | None, float], Awaitable[tuple[Transport, DeviceInfo | None]]]
"""``(device_id, scan_timeout) -> (transport, device)``; injectable for tests."""

EXIT_INTERNAL = 1
EXIT_USAGE = 2


async def _ble_factory(
    device_id: str | None, scan_timeout: float
) -> tuple[Transport, DeviceInfo | None]:
    from openvave.transport.ble import open_ble

    return await open_ble(device_id, scan_timeout)


def _global_options(parser: argparse.ArgumentParser, *, suppress: bool) -> None:
    """Options valid before and after the subcommand (subparser copies don't override)."""

    def default(value: object) -> object:
        return argparse.SUPPRESS if suppress else value

    parser.add_argument(
        "--json",
        action="store_true",
        default=default(False),
        help="emit one JSON document on stdout",
    )
    parser.add_argument(
        "--device",
        metavar="ID",
        default=default(None),
        help="connect to this platform identifier (skips the name filter)",
    )
    parser.add_argument(
        "--scan-timeout",
        metavar="SECONDS",
        type=float,
        default=default(DEFAULT_SCAN_TIMEOUT),
        help="max scan time (default 5)",
    )
    parser.add_argument(
        "--timeout",
        metavar="SECONDS",
        type=float,
        default=default(DEFAULT_TIMEOUT),
        help="per-request timeout (default 2)",
    )
    parser.add_argument(
        "--trace",
        action="store_true",
        default=default(False),
        help="hex trace of every frame on stderr",
    )


def _write_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--dry-run", action="store_true", help="do the reads and print the frame; send no write"
    )
    parser.add_argument(
        "--experimental",
        action="store_true",
        help="allow writes not yet confirmed in the protocol docs, or on untested firmware",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openvave",
        description="Client for the M-VAVE Tank-G pedal: reads, backups and guarded "
        "edit-buffer writes (never saved). Unofficial. "
        "Not affiliated with or endorsed by M-VAVE / Cuvave.",
    )
    parser.add_argument("--version", action="version", version=f"openvave {__version__}")
    _global_options(parser, suppress=False)
    common = argparse.ArgumentParser(add_help=False)
    _global_options(common, suppress=True)
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.add_parser("info", parents=[common], help="identify the pedal and read its state regions")
    preset = sub.add_parser("preset", parents=[common], help="read the current or stored presets")
    preset_sub = preset.add_subparsers(dest="action", metavar="ACTION", required=True)
    preset_sub.add_parser("dump", parents=[common], help="print the 21-byte current preset buffer")
    backup = preset_sub.add_parser(
        "backup",
        parents=[common],
        help="save all 36 stored presets to a verified JSON backup file (read-only)",
    )
    backup.add_argument(
        "--output",
        metavar="PATH",
        default=None,
        help="backup file (default ./tankg-backup-<YYYYmmdd-HHMMSS>.json)",
    )
    backup.add_argument("--force", action="store_true", help="overwrite an existing file")
    select = preset_sub.add_parser(
        "select",
        parents=[common],
        help="load a stored preset (1A–9D or 0–35) with the preset-select write",
    )
    select.add_argument("position", help="1A–9D (case-insensitive) or index 0–35")
    _write_options(select)
    select.add_argument(
        "--discard-edits",
        action="store_true",
        help="select even in edit mode (the pedal's unsaved edits are lost)",
    )
    reload = preset_sub.add_parser(
        "reload",
        parents=[common],
        help="discard unsaved edits: load the current preset again from its stored copy",
    )
    _write_options(reload)
    reload.add_argument(
        "--discard-edits",
        action="store_true",
        help="reload even in edit mode (the pedal's unsaved edits are lost)",
    )
    typed = "; ".join(f"{name}: {', '.join(types)}" for name, types in TYPED_FIELDS.items())
    set_parser = sub.add_parser(
        "set",
        parents=[common],
        help="change one field of the current preset (normal or edit mode; not saved)",
        description="Writable fields: " + ", ".join(WRITABLE_FIELDS) + ". Works in normal and "
        "edit mode. The change is not saved: 'openvave preset reload' discards it. "
        f"Knobs that run through types ({typed}) take a position 1–{REVERB_SECTION_STEPS} "
        "inside a type: 'set reverb_decay 12 --type room'; without --type the preset's current "
        "type is kept; --raw writes the raw byte 0–127.",
    )
    set_parser.add_argument("field", help="byte map field name, e.g. gain, mod_on, led_colour")
    set_parser.add_argument(
        "value",
        help="0–127, 0–8, on/off, #rrggbb / r,g,b; for a typed knob a position 1–40",
    )
    set_parser.add_argument(
        "--type",
        dest="knob_type",
        metavar="TYPE",
        default=None,
        help="type of a typed knob (reverb_decay: room, spring, cloud)",
    )
    set_parser.add_argument(
        "--raw", action="store_true", help="for a typed knob: the value is the raw byte 0–127"
    )
    _write_options(set_parser)
    watch_parser = sub.add_parser(
        "watch",
        parents=[common],
        help="poll the pedal and print/record every byte that changes (read-only)",
        description="Poll global, current preset and status; type a label and Enter before "
        "each step, q to quit. With --json: JSON Lines, one event per line.",
    )
    watch_parser.add_argument(
        "--interval",
        metavar="SECONDS",
        type=float,
        default=0.5,
        help="time between poll cycles (default 0.5, minimum 0.2)",
    )
    watch_parser.add_argument(
        "--duration", metavar="SECONDS", type=float, default=None, help="stop after this long"
    )
    record = watch_parser.add_mutually_exclusive_group()
    record.add_argument(
        "--record",
        metavar="PATH",
        default=None,
        help="session record file (default captures/private/<YYYYMMDD-HHMMSS>-watch.jsonl)",
    )
    record.add_argument("--no-record", action="store_true", help="do not write a session record")
    return parser


class _StderrFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return f"{record.levelname.lower()}: {record.getMessage()}"


@contextmanager
def _logging(trace: bool) -> Iterator[None]:
    """Route library warnings (and the trace, if asked) to stderr for one CLI run."""
    base = logging.getLogger("openvave")
    trace_logger = logging.getLogger("openvave.trace")
    warn_handler = logging.StreamHandler(sys.stderr)
    warn_handler.setLevel(logging.WARNING)
    warn_handler.setFormatter(_StderrFormatter())
    saved = (base.propagate, base.level, trace_logger.propagate, trace_logger.level)
    base.addHandler(warn_handler)
    base.propagate = False
    if base.level == logging.NOTSET or base.level > logging.WARNING:
        base.setLevel(logging.WARNING)
    trace_handler: logging.Handler | None = None
    if trace:
        trace_handler = logging.StreamHandler(sys.stderr)
        trace_handler.setFormatter(logging.Formatter("%(message)s"))
        trace_logger.addHandler(trace_handler)
        trace_logger.setLevel(logging.DEBUG)
        trace_logger.propagate = False
    try:
        yield
    finally:
        base.removeHandler(warn_handler)
        if trace_handler is not None:
            trace_logger.removeHandler(trace_handler)
        base.propagate, _, trace_logger.propagate, _ = saved
        base.setLevel(saved[1])
        trace_logger.setLevel(saved[3])


async def _info(args: argparse.Namespace, factory: TransportFactory) -> str:
    async def source() -> tuple[Transport, DeviceInfo | None]:
        return await factory(args.device, args.scan_timeout)

    async with TankG(source, timeout=args.timeout) as pedal:
        snapshot = await pedal.snapshot()
    if args.json:
        return render.dumps(render.info_json(snapshot))
    return render.human_info(snapshot)


async def _preset_dump(args: argparse.Namespace, factory: TransportFactory) -> str:
    async def source() -> tuple[Transport, DeviceInfo | None]:
        return await factory(args.device, args.scan_timeout)

    async with TankG(source, timeout=args.timeout) as pedal:
        state, _, read, _ = await pedal._read_state()
        identity, device = pedal.identity, pedal.device
    if args.json:
        document = render.preset_json(read, datetime.now(UTC), device, identity)
        document["pedal_state"] = state.label
        return render.dumps(document)
    return render.human_preset(read, identity, state)


async def _preset_backup(args: argparse.Namespace, factory: TransportFactory) -> str:
    async def source() -> tuple[Transport, DeviceInfo | None]:
        return await factory(args.device, args.scan_timeout)

    async with TankG(source, timeout=args.timeout) as pedal:
        backup = await pedal.backup()
        device = pedal.device
    if "unexpected_header" in backup.warnings:
        print(
            f"warning: unexpected stored-image header {backup.header.hex(' ')} "
            "(expected a5 5a); the backup is saved, but the layout may differ",
            file=sys.stderr,
        )
    document = backup.to_document()
    files.write_json_atomic(args.output, document, force=args.force)
    if args.json:
        return render.dumps(render.backup_json(backup, document, device, str(args.output)))
    return render.human_backup(backup, str(args.output))


class UsageError(Exception):
    """A command-line value that cannot be used (exit 2, nothing sent)."""


_COLOUR_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_COLOUR_RGB = re.compile(r"^\s*-?\d+\s*,\s*-?\d+\s*,\s*-?\d+\s*$")
_INTEGER = re.compile(r"^-?\d+$")


def parse_typed_value(field: str, text: str, knob_type: str | None, raw: bool) -> FieldValue:
    """A typed knob's value (spec 004 R3): a position 1–40 in ``knob_type`` (``None``: keep the
    current type), or the raw byte with ``raw``. :class:`UsageError` when unusable."""
    types = TYPED_FIELDS[field]
    if raw:
        if knob_type is not None:
            raise UsageError("--raw takes a raw byte 0–127; it cannot be combined with --type")
        if not _INTEGER.match(text):
            raise UsageError(f"{field} --raw takes an integer 0–127, got {text!r}")
        return int(text)
    if knob_type is not None and knob_type.lower() not in types:
        raise UsageError(f"{field} type must be one of {', '.join(types)}, got {knob_type!r}")
    if not _INTEGER.match(text) or not 1 <= int(text) <= REVERB_SECTION_STEPS:
        raise UsageError(
            f"{field} takes a position 1–{REVERB_SECTION_STEPS} inside a type "
            f"(or --raw 0–127), got {text!r}"
        )
    return (None if knob_type is None else knob_type.lower(), int(text))


def parse_field_value(
    field: str, text: str, knob_type: str | None = None, raw: bool = False
) -> FieldValue:
    """Command-line value for ``openvave set``; :class:`UsageError` for an unusable one.

    Range is not checked here: an out-of-range value is a refusal (exit 1) from the library.
    For a field in ``TYPED_FIELDS`` the value is a position inside ``knob_type`` (or the raw
    byte with ``raw``); ``--type`` / ``--raw`` on any other field is a usage error.
    """
    spec = WRITABLE_FIELDS.get(field)
    if spec is None:
        raise UsageError(f"unknown field {field!r}; writable fields: {', '.join(WRITABLE_FIELDS)}")
    if field in TYPED_FIELDS:
        return parse_typed_value(field, text, knob_type, raw)
    if knob_type is not None or raw:
        raise UsageError(
            f"--type / --raw apply only to knobs with types: {', '.join(sorted(TYPED_FIELDS))}"
        )
    if spec.kind == "led_colour":
        if _COLOUR_HEX.match(text):
            r, g, b = bytes.fromhex(text[1:])
            return (r, g, b)
        if _COLOUR_RGB.match(text):
            r, g, b = (int(part) for part in text.split(","))
            return (r, g, b)
        raise UsageError(f"led_colour takes #rrggbb or r,g,b (0–255 each), got {text!r}")
    if spec.kind == "block_switch":
        if text.lower() in ("on", "off"):
            return text.lower() == "on"
        raise UsageError(f"{field} takes on or off, got {text!r}")
    entry = spec.entry
    assert entry is not None
    if _INTEGER.match(text):
        return int(text)
    raise UsageError(f"{field} takes an integer {entry.min}–{entry.max}, got {text!r}")


def _render_write(
    args: argparse.Namespace,
    command: str,
    plan: WritePlan,
    result: WriteResult | None,
    pedal: TankG,
) -> str:
    if args.json:
        return render.dumps(
            render.write_json(
                command,
                plan,
                result,
                dry_run=args.dry_run,
                read_at=datetime.now(UTC),
                device=pedal.device,
                identity=pedal.identity,
            )
        )
    if command == "set":
        return render.human_set(plan, result, dry_run=args.dry_run)
    if command == "preset reload":
        return render.human_reload(plan, result, dry_run=args.dry_run)
    return render.human_select(plan, result, dry_run=args.dry_run)


async def _write(
    args: argparse.Namespace,
    factory: TransportFactory,
    command: str,
    plan_call: Callable[[TankG], Awaitable[WritePlan]],
    write_call: Callable[[TankG], Awaitable[WriteResult]],
) -> str:
    async def source() -> tuple[Transport, DeviceInfo | None]:
        return await factory(args.device, args.scan_timeout)

    async with TankG(source, timeout=args.timeout) as pedal:
        if args.dry_run:
            return _render_write(args, command, await plan_call(pedal), None, pedal)
        try:
            result = await write_call(pedal)
        except WriteNotAppliedError as err:
            if not args.json:  # 001 rule: with --json, stdout stays empty on failure
                print(_render_write(args, command, err.result.plan, err.result, pedal))
            raise
        return _render_write(args, command, result.plan, result, pedal)


async def _set(args: argparse.Namespace, factory: TransportFactory) -> str:
    field, value, experimental = args.field, args.parsed_value, args.experimental
    return await _write(
        args,
        factory,
        "set",
        lambda p: p.plan_set(field, value, experimental=experimental),
        lambda p: p.set_field(field, value, experimental=experimental),
    )


async def _preset_select(args: argparse.Namespace, factory: TransportFactory) -> str:
    index, discard, experimental = args.index, args.discard_edits, args.experimental
    return await _write(
        args,
        factory,
        "preset select",
        lambda p: p.plan_select(index, discard_edits=discard, experimental=experimental),
        lambda p: p.select_preset(index, discard_edits=discard, experimental=experimental),
    )


async def _preset_reload(args: argparse.Namespace, factory: TransportFactory) -> str:
    discard, experimental = args.discard_edits, args.experimental
    return await _write(
        args,
        factory,
        "preset reload",
        lambda p: p.plan_reload(discard_edits=discard, experimental=experimental),
        lambda p: p.reload_preset(discard_edits=discard, experimental=experimental),
    )


async def _preset(args: argparse.Namespace, factory: TransportFactory) -> str:
    if args.action == "backup":
        return await _preset_backup(args, factory)
    if args.action == "select":
        return await _preset_select(args, factory)
    if args.action == "reload":
        return await _preset_reload(args, factory)
    return await _preset_dump(args, factory)


COMMANDS: dict[
    str, Callable[[argparse.Namespace, TransportFactory], Coroutine[None, None, str]]
] = {
    "info": _info,
    "preset": _preset,
    "set": _set,
}


def _prepare_write(args: argparse.Namespace) -> None:
    """Parse the field value / position before any pedal I/O (usage errors exit 2)."""
    if args.command == "set":
        args.parsed_value = parse_field_value(args.field, args.value, args.knob_type, args.raw)
    else:
        try:
            args.index = parse_position(args.position)
        except ValueError as err:
            raise UsageError(str(err)) from None


def _prepare_backup(args: argparse.Namespace) -> None:
    """Resolve the backup target and refuse an existing one before any pedal I/O."""
    if args.output is None:
        args.output = Path(f"tankg-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json")
    else:
        args.output = Path(args.output)
    files.check_target(args.output, force=args.force)


def _report(err: OpenvaveError) -> None:
    print(f"error: {err}", file=sys.stderr)
    if isinstance(err, MultipleDevicesError):
        for c in err.candidates:
            rssi = f"{c.rssi} dBm" if c.rssi is not None else "? dBm"
            print(f"  {c.identifier}  {c.name}  {rssi}", file=sys.stderr)
        print("hint: re-run with --device <identifier>", file=sys.stderr)
    elif isinstance(err, BluetoothUnavailableError):
        if sys.platform == "darwin":
            print(
                "hint: turn Bluetooth on, and allow your terminal app under System Settings > "
                "Privacy & Security > Bluetooth",
                file=sys.stderr,
            )
        else:
            print("hint: turn Bluetooth on and check this user may access it", file=sys.stderr)
    elif isinstance(err, WriteNotAppliedError):
        print(
            "hint: the pedal acknowledged the write but the re-read does not show it; nothing "
            "was retried. 'openvave preset reload' loads the stored preset again.",
            file=sys.stderr,
        )
    elif err.exit_code == 3:
        print(
            "hint: switch the pedal on and close the M-VAVE phone app (it holds the connection)",
            file=sys.stderr,
        )


def main(
    argv: Sequence[str] | None = None,
    *,
    transport_factory: TransportFactory | None = None,
    stdin: watch.LineSource | None = None,
    clock: watch.Clock | None = None,
) -> int:
    """Run the CLI and return its exit code (contracts/cli.md).

    ``transport_factory``, ``stdin`` (watch labels) and ``clock`` (watch timing) are injectable
    for tests.
    """
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exit_:
        return exit_.code if isinstance(exit_.code, int) else EXIT_USAGE
    if args.command is None:
        parser.print_help(sys.stderr)
        return EXIT_USAGE
    if args.command == "watch":
        try:
            watch.validate(args)
        except watch.UsageError as err:
            print(f"openvave watch: error: {err}", file=sys.stderr)
            return EXIT_USAGE
    if args.command == "preset" and args.action == "backup":
        try:
            _prepare_backup(args)
        except files.TargetExistsError as err:
            print(f"openvave preset backup: error: {err}", file=sys.stderr)
            return EXIT_USAGE
    if args.command == "set" or (args.command == "preset" and args.action == "select"):
        try:
            _prepare_write(args)
        except UsageError as err:
            name = "set" if args.command == "set" else "preset select"
            print(f"openvave {name}: error: {err}", file=sys.stderr)
            return EXIT_USAGE
    factory = transport_factory or _ble_factory
    debug = os.environ.get("OPENVAVE_DEBUG") == "1"
    with _logging(args.trace):
        try:
            if args.command == "watch":
                return asyncio.run(
                    watch.run(args, factory, stdin or sys.stdin, clock or watch.SystemClock())
                )
            output = asyncio.run(COMMANDS[args.command](args, factory))
        except files.TargetExistsError as err:
            print(f"openvave preset backup: error: {err}", file=sys.stderr)
            return EXIT_USAGE
        except OpenvaveError as err:
            if debug:
                traceback.print_exc()
            _report(err)
            return err.exit_code
        except KeyboardInterrupt:
            print("error: interrupted", file=sys.stderr)
            return 130
        except Exception as err:  # noqa: BLE001 - last-resort handler, exit 1
            if debug:
                traceback.print_exc()
            print(f"error: unexpected {type(err).__name__}: {err}", file=sys.stderr)
            print("hint: re-run with OPENVAVE_DEBUG=1 and report the traceback", file=sys.stderr)
            return EXIT_INTERNAL
    print(output)
    return 0
