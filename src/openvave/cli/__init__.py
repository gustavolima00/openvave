"""``openvave`` command-line interface (contracts/cli.md).

Parses arguments, runs one session, renders the result. Results go to stdout; errors, warnings
and the hex trace go to stderr. Exit codes are part of the public contract.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import traceback
from collections.abc import Awaitable, Callable, Coroutine, Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime

from openvave import __version__
from openvave.cli import render, watch
from openvave.errors import BluetoothUnavailableError, MultipleDevicesError, OpenvaveError
from openvave.models import DeviceInfo, Region
from openvave.session import DEFAULT_SCAN_TIMEOUT, DEFAULT_TIMEOUT, TankG
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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openvave",
        description="Read-only client for the M-VAVE Tank-G pedal. Unofficial. "
        "Not affiliated with or endorsed by M-VAVE / Cuvave.",
    )
    parser.add_argument("--version", action="version", version=f"openvave {__version__}")
    _global_options(parser, suppress=False)
    common = argparse.ArgumentParser(add_help=False)
    _global_options(common, suppress=True)
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.add_parser("info", parents=[common], help="identify the pedal and read its state regions")
    preset = sub.add_parser("preset", parents=[common], help="read the current preset")
    preset_sub = preset.add_subparsers(dest="action", metavar="ACTION", required=True)
    preset_sub.add_parser("dump", parents=[common], help="print the 21-byte current preset buffer")
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
        read = await pedal.read(Region.CURRENT_PRESET)
        identity, device = pedal.identity, pedal.device
    if args.json:
        return render.dumps(render.preset_json(read, datetime.now(UTC), device, identity))
    return render.human_preset(read, identity)


COMMANDS: dict[
    str, Callable[[argparse.Namespace, TransportFactory], Coroutine[None, None, str]]
] = {
    "info": _info,
    "preset": _preset_dump,
}


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
    factory = transport_factory or _ble_factory
    debug = os.environ.get("OPENVAVE_DEBUG") == "1"
    with _logging(args.trace):
        try:
            if args.command == "watch":
                return asyncio.run(
                    watch.run(args, factory, stdin or sys.stdin, clock or watch.SystemClock())
                )
            output = asyncio.run(COMMANDS[args.command](args, factory))
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
