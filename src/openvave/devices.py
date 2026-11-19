"""Known pedals, their file, and the rule that chooses the pedal a command acts on (spec 005).

Pure apart from :meth:`KnownDevices.load` and :meth:`KnownDevices.save`, which read and write the
file. Nothing here touches Bluetooth, and nothing in the library calls into this module on its
own: a configuration is read only when the caller asks for it (FR-028).

File format: ``specs/005-device-selection/contracts/devices-file.schema.json`` (research R1–R2).
Identifier and nickname rules: research R3. Choice order: research R5.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from openvave.errors import ConfigError

FORMAT_VERSION = 1
"""The ``format_version`` this library reads and writes."""

TargetSource = Literal["device_option", "environment", "selected"]
"""Where a :class:`Target` came from (``only_one_found`` is never a target)."""

_HEX = "[0-9A-Fa-f]"
_MAC = re.compile(rf"^{_HEX}{{2}}([:-]){_HEX}{{2}}(?:\1{_HEX}{{2}}){{4}}$")
_UUID = re.compile(rf"^{_HEX}{{8}}-{_HEX}{{4}}-{_HEX}{{4}}-{_HEX}{{4}}-{_HEX}{{12}}$")
_NICKNAME = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
_ALL_HEX = re.compile(rf"^{_HEX}{{4,}}$")
_DEVICE_FIELDS = (
    "identifier",
    "nickname",
    "added_at",
    "selected_at",
    "last_name",
    "last_firmware",
    "last_seen_at",
)


def is_identifier(value: str) -> bool:
    """True when ``value`` has the shape of a platform identifier: a MAC address
    (``AA:BB:CC:DD:EE:FF``, ``:`` or ``-``) or a UUID (``8-4-4-4-12`` hex), any case."""
    return bool(_MAC.match(value) or _UUID.match(value))


def check_nickname(value: str) -> str:
    """Return ``value`` when it is a valid nickname, else raise ``ConfigError("bad_nickname")``.

    Valid: 1–32 characters of ``A-Z a-z 0-9 _ -``, not shaped like an identifier, and not all hex
    digits of length 4 or more (so a nickname is never mistaken for an identifier prefix, R4).
    """
    if not _NICKNAME.match(value):
        problem = f"bad nickname {value!r}: use 1 to 32 letters, digits, '_' or '-'"
    elif is_identifier(value) or _ALL_HEX.match(value):
        problem = (
            f"bad nickname {value!r}: it looks like an identifier "
            "(4 or more hex digits); add a letter outside a-f"
        )
    else:
        return value
    raise ConfigError(problem, reason="bad_nickname")


def default_config_path() -> Path:
    """Where the known-pedals file is, in this order (research R1): ``$OPENVAVE_CONFIG``;
    ``$XDG_CONFIG_HOME/openvave/devices.json``; on Windows ``%APPDATA%\\openvave\\devices.json``;
    otherwise ``~/.config/openvave/devices.json``. Empty variables count as unset."""
    explicit = os.environ.get("OPENVAVE_CONFIG")
    if explicit:
        return Path(explicit).expanduser()
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "openvave" / "devices.json"
    appdata = os.environ.get("APPDATA")
    if sys.platform == "win32" and appdata:
        return Path(appdata) / "openvave" / "devices.json"
    return Path.home() / ".config" / "openvave" / "devices.json"


def _now() -> datetime:
    return datetime.now(UTC)


def _same(a: str, b: str) -> bool:
    return a.casefold() == b.casefold()


@dataclass(frozen=True)
class KnownDevice:
    """A pedal the owner has selected at least once (spec 005 data model)."""

    identifier: str
    """MAC (Linux/Windows) or CoreBluetooth UUID (macOS), as the platform reported it. On macOS
    it is specific to this computer."""
    nickname: str | None
    """The owner's name for it, or ``None``."""
    added_at: datetime
    """When it was first selected (UTC)."""
    selected_at: datetime | None = None
    """The last time it became the default (UTC)."""
    last_name: str | None = None
    """Advertised name last seen."""
    last_firmware: int | None = None
    """Firmware reported by the last handshake."""
    last_seen_at: datetime | None = None
    """Last successful connection or identify (UTC)."""
    extra: Mapping[str, Any] = field(default_factory=dict, repr=False, hash=False)
    """Keys of the file's device entry that this version does not know; written back as read."""


@dataclass(frozen=True)
class Target:
    """The pedal a command must act on, chosen before any scan (research R5)."""

    identifier: str
    """What the scan waits for (compared case-insensitively)."""
    nickname: str | None
    """Its nickname when it is a known pedal."""
    chosen_by: TargetSource
    """``"device_option"`` (``--device``), ``"environment"`` (``OPENVAVE_DEVICE``) or
    ``"selected"`` (the default pedal)."""


@dataclass(frozen=True)
class KnownDevices:
    """The known pedals and the default: the content of ``devices.json``.

    Immutable: every operation returns a new value; :meth:`save` writes it. Identifiers and
    nicknames are compared case-insensitively.
    """

    path: Path
    """Where it was loaded from and where :meth:`save` writes."""
    devices: tuple[KnownDevice, ...] = ()
    """Known pedals, in the order they were first selected."""
    default_identifier: str | None = None
    """Identifier of the default pedal; one of ``devices`` or ``None``."""
    extra: Mapping[str, Any] = field(default_factory=dict, repr=False, hash=False)
    """Top-level keys of the file that this version does not know; written back as read."""

    # --- reading -----------------------------------------------------------------------------

    @property
    def default(self) -> KnownDevice | None:
        """The default pedal, or ``None``."""
        if self.default_identifier is None:
            return None
        return self._by_identifier(self.default_identifier)

    @property
    def nicknames(self) -> tuple[str, ...]:
        """Nicknames of the known pedals, in order."""
        return tuple(d.nickname for d in self.devices if d.nickname)

    def find(self, value: str) -> KnownDevice | None:
        """The known pedal whose identifier or nickname is ``value`` (any case), or ``None``."""
        return self._by_identifier(value) or next(
            (d for d in self.devices if d.nickname is not None and _same(d.nickname, value)), None
        )

    def _by_identifier(self, identifier: str) -> KnownDevice | None:
        return next((d for d in self.devices if _same(d.identifier, identifier)), None)

    def _require(self, target: str) -> KnownDevice:
        device = self.find(target)
        if device is None:
            raise ConfigError(f"no known pedal {target!r}", reason="unknown_device", path=self.path)
        return device

    def _check_free(self, nickname: str, owner: str | None) -> str:
        check_nickname(nickname)
        other = next(
            (
                d
                for d in self.devices
                if d.nickname is not None
                and _same(d.nickname, nickname)
                and (owner is None or not _same(d.identifier, owner))
            ),
            None,
        )
        if other is not None:
            raise ConfigError(
                f"nickname {nickname!r} is already used by {other.identifier}",
                reason="nickname_in_use",
                path=self.path,
            )
        return nickname

    def _replace_device(self, device: KnownDevice) -> tuple[KnownDevice, ...]:
        return tuple(device if _same(d.identifier, device.identifier) else d for d in self.devices)

    # --- operations --------------------------------------------------------------------------

    def select(
        self,
        identifier: str,
        nickname: str | None = None,
        *,
        name: str | None = None,
        now: datetime | None = None,
    ) -> KnownDevices:
        """Make ``identifier`` the default, adding it when new. ``nickname`` (re)names it; ``name``
        records its advertised name. The previous default stays known.

        Raises ``ConfigError`` (``bad_nickname``, ``nickname_in_use``)."""
        when = now or _now()
        current = self._by_identifier(identifier)
        if nickname is not None:
            self._check_free(nickname, current.identifier if current else None)
        if current is None:
            device = KnownDevice(
                identifier=identifier,
                nickname=nickname,
                added_at=when,
                selected_at=when,
                last_name=name,
            )
            devices = (*self.devices, device)
        else:
            device = replace(
                current,
                nickname=nickname if nickname is not None else current.nickname,
                selected_at=when,
                last_name=name if name is not None else current.last_name,
            )
            devices = self._replace_device(device)
        return replace(self, devices=devices, default_identifier=device.identifier)

    def rename(self, target: str, new: str) -> KnownDevices:
        """Give the known pedal ``target`` (nickname or identifier) the nickname ``new``.

        Raises ``ConfigError`` (``unknown_device``, ``bad_nickname``, ``nickname_in_use``)."""
        device = self._require(target)
        self._check_free(new, device.identifier)
        return replace(self, devices=self._replace_device(replace(device, nickname=new)))

    def forget(self, target: str | None = None) -> KnownDevices:
        """Without ``target``: clear the default (the pedals stay known). With ``target``
        (nickname or identifier): remove that pedal, and the default when it was it.

        Raises ``ConfigError("unknown_device")`` for an unknown ``target``."""
        if target is None:
            return replace(self, default_identifier=None)
        device = self._require(target)
        default = self.default_identifier
        if default is not None and _same(default, device.identifier):
            default = None
        devices = tuple(d for d in self.devices if d is not device)
        return replace(self, devices=devices, default_identifier=default)

    def forget_all(self) -> KnownDevices:
        """No known pedal and no default (unknown top-level keys are kept)."""
        return replace(self, devices=(), default_identifier=None)

    def record_seen(
        self,
        identifier: str,
        name: str | None,
        firmware: int | None,
        now: datetime | None = None,
    ) -> KnownDevices:
        """Update ``last_name``, ``last_firmware`` and ``last_seen_at`` of a known pedal; an
        unknown identifier changes nothing (research R9)."""
        current = self._by_identifier(identifier)
        if current is None:
            return self
        device = replace(
            current, last_name=name, last_firmware=firmware, last_seen_at=now or _now()
        )
        return replace(self, devices=self._replace_device(device))

    # --- the file ----------------------------------------------------------------------------

    @classmethod
    def load(cls, path: Path | str | None = None) -> KnownDevices:
        """Read the file at ``path`` (default: :func:`default_config_path`). A missing file is
        an empty configuration. Raises ``ConfigError("invalid_file")`` naming the path when the
        file cannot be read or is not valid (research R2)."""
        file = Path(path) if path is not None else default_config_path()
        try:
            text = file.read_text(encoding="utf-8")
        except FileNotFoundError:
            return cls(path=file)
        except (OSError, UnicodeDecodeError) as exc:
            raise _invalid(file, f"cannot be read ({exc.__class__.__name__}: {exc})") from exc
        try:
            document = json.loads(text)
        except json.JSONDecodeError as exc:
            raise _invalid(file, f"not valid JSON ({exc.msg}, line {exc.lineno})") from exc
        return _from_document(file, document)

    def save(self) -> None:
        """Write the file atomically (temporary file in the same directory, then replace),
        creating the directory, with mode ``0600`` where the platform has modes."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            dir=self.path.parent, prefix=f".{self.path.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(_to_document(self), handle, indent=2, ensure_ascii=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            if os.name == "posix":
                os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(temporary)
            raise


def resolve_target(
    option: str | None, environment: str | None, known: KnownDevices | None
) -> Target | None:
    """Choose the pedal before any Bluetooth use (research R5, pure).

    Order: ``option`` (``--device``), then ``environment`` (``OPENVAVE_DEVICE``), then the
    default of ``known``. An identifier-shaped value is used as is (with its nickname when
    known); any other value must be a known nickname, else ``ConfigError("unknown_nickname")``
    listing the known nicknames. Empty strings count as unset. ``None``: no choice, the 0.4.0
    scan rules apply (the only Tank-G in range).
    """
    for value, source in ((option, "device_option"), (environment, "environment")):
        if value:
            return _target_for(value, source, known)  # type: ignore[arg-type]
    default = known.default if known is not None else None
    if default is not None:
        return Target(default.identifier, default.nickname, "selected")
    return None


def _target_for(value: str, source: TargetSource, known: KnownDevices | None) -> Target:
    found = known.find(value) if known is not None else None
    if is_identifier(value):
        return Target(value, found.nickname if found else None, source)
    if found is not None:
        return Target(found.identifier, found.nickname, source)
    nicknames = known.nicknames if known is not None else ()
    listed = (
        "known nicknames: " + ", ".join(nicknames)
        if nicknames
        else "no known pedal has a nickname (see: openvave device)"
    )
    raise ConfigError(
        f"unknown pedal nickname {value!r}; {listed}",
        reason="unknown_nickname",
        path=None,
    )


# --- file document <-> values --------------------------------------------------------------


def _invalid(path: Path, problem: str) -> ConfigError:
    return ConfigError(problem, reason="invalid_file", path=path)


def _time_text(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat() if value is not None else None


def _to_document(known: KnownDevices) -> dict[str, Any]:
    document: dict[str, Any] = {
        "format_version": FORMAT_VERSION,
        "default": known.default_identifier,
        "devices": [
            {
                **dict(d.extra),
                "identifier": d.identifier,
                "nickname": d.nickname,
                "added_at": _time_text(d.added_at),
                "selected_at": _time_text(d.selected_at),
                "last_name": d.last_name,
                "last_firmware": d.last_firmware,
                "last_seen_at": _time_text(d.last_seen_at),
            }
            for d in known.devices
        ],
    }
    for key, value in known.extra.items():
        document.setdefault(key, value)
    return document


def _from_document(path: Path, document: Any) -> KnownDevices:
    if not isinstance(document, dict):
        raise _invalid(path, "not a JSON object")
    for key in ("format_version", "default", "devices"):
        if key not in document:
            raise _invalid(path, f"missing {key!r}")
    version = document["format_version"]
    if type(version) is not int or version != FORMAT_VERSION:
        raise _invalid(path, f"unsupported format_version {version!r} (expected {FORMAT_VERSION})")
    if not isinstance(document["devices"], list):
        raise _invalid(path, "'devices' is not a list")
    default = document["default"]
    if default is not None and not isinstance(default, str):
        raise _invalid(path, "'default' is not a string or null")
    devices: list[KnownDevice] = []
    for index, entry in enumerate(document["devices"]):
        device = _device_from(path, index, entry)
        for other in devices:
            if _same(other.identifier, device.identifier):
                raise _invalid(path, f"identifier {device.identifier!r} appears twice")
            if other.nickname and device.nickname and _same(other.nickname, device.nickname):
                raise _invalid(path, f"nickname {device.nickname!r} appears twice")
        devices.append(device)
    if default is not None and not any(_same(d.identifier, default) for d in devices):
        raise _invalid(path, f"default {default!r} is not one of the devices")
    extra = {k: v for k, v in document.items() if k not in ("format_version", "default", "devices")}
    return KnownDevices(path=path, devices=tuple(devices), default_identifier=default, extra=extra)


def _device_from(path: Path, index: int, entry: Any) -> KnownDevice:
    where = f"devices[{index}]"
    if not isinstance(entry, dict):
        raise _invalid(path, f"{where} is not an object")
    for key in _DEVICE_FIELDS:
        if key not in entry:
            raise _invalid(path, f"{where} is missing {key!r}")
    identifier = entry["identifier"]
    if not isinstance(identifier, str) or not identifier:
        raise _invalid(path, f"{where}.identifier is not a non-empty string")
    nickname = entry["nickname"]
    if nickname is not None and (not isinstance(nickname, str) or not _NICKNAME.match(nickname)):
        raise _invalid(path, f"{where}.nickname {nickname!r} is not a valid nickname")
    last_name = entry["last_name"]
    if last_name is not None and not isinstance(last_name, str):
        raise _invalid(path, f"{where}.last_name is not a string or null")
    firmware = entry["last_firmware"]
    if firmware is not None and (type(firmware) is not int or firmware < 0):
        raise _invalid(path, f"{where}.last_firmware is not a non-negative integer or null")
    added_at = _time_from(path, f"{where}.added_at", entry["added_at"])
    if added_at is None:
        raise _invalid(path, f"{where}.added_at is null")
    return KnownDevice(
        identifier=identifier,
        nickname=nickname,
        added_at=added_at,
        selected_at=_time_from(path, f"{where}.selected_at", entry["selected_at"]),
        last_name=last_name,
        last_firmware=firmware,
        last_seen_at=_time_from(path, f"{where}.last_seen_at", entry["last_seen_at"]),
        extra={k: v for k, v in entry.items() if k not in _DEVICE_FIELDS},
    )


def _time_from(path: Path, where: str, value: Any) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise _invalid(path, f"{where} is not a time string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise _invalid(path, f"{where} {value!r} is not an ISO 8601 time") from exc
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed
