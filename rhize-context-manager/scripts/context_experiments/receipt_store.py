"""Permission-restricted, append-only receipt persistence."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Iterable

from .models import ExperimentReceipt


_SAFE_FILE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


class ReceiptStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def write(self, receipt: ExperimentReceipt) -> Path:
        if not _SAFE_FILE_ID.fullmatch(receipt.experiment_id):
            raise ValueError("experiment id is not safe for a receipt filename")
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        destination = self.directory / f"{receipt.experiment_id}.json"
        if destination.exists():
            raise FileExistsError(f"receipt already exists: {receipt.experiment_id}")
        descriptor, temporary_name = tempfile.mkstemp(prefix=".receipt-", dir=self.directory)
        temporary = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            payload = (json.dumps(receipt.to_dict(), indent=2, sort_keys=True) + "\n").encode()
            os.write(descriptor, payload)
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = -1
            if destination.exists():
                raise FileExistsError(f"receipt already exists: {receipt.experiment_id}")
            os.link(temporary, destination)
            temporary.unlink()
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            temporary.unlink(missing_ok=True)
        return destination

    def documents(self) -> Iterable[dict]:
        if not self.directory.exists():
            return ()
        documents: list[dict] = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(value, dict):
                documents.append(value)
        return tuple(documents)


class PendingStore:
    """Session-keyed pending selections; contains no prompt or absolute repo path."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def write(self, session_id_hash: str, document: dict) -> Path:
        if not _SAFE_FILE_ID.fullmatch(session_id_hash):
            raise ValueError("session id hash is not safe for a pending filename")
        _assert_pending_safe(document)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        destination = self.directory / f"{session_id_hash}.json"
        if destination.exists():
            raise FileExistsError("this session already has a pending context experiment")
        descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            os.write(descriptor, (json.dumps(document, sort_keys=True) + "\n").encode())
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return destination

    def read(self, session_id_hash: str) -> dict | None:
        if not _SAFE_FILE_ID.fullmatch(session_id_hash):
            return None
        path = self.directory / f"{session_id_hash}.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return None
        if not isinstance(value, dict):
            return None
        try:
            _assert_pending_safe(value)
        except ValueError:
            return None
        return value

    def delete(self, session_id_hash: str) -> None:
        if _SAFE_FILE_ID.fullmatch(session_id_hash):
            (self.directory / f"{session_id_hash}.json").unlink(missing_ok=True)


def _assert_pending_safe(value: object, key: str = "") -> None:
    if key in {"prompt", "repoRoot", "source", "sourceText", "code"}:
        raise ValueError(f"pending selection contains forbidden field: {key}")
    if isinstance(value, dict):
        for child_key, child_value in value.items():
            _assert_pending_safe(child_value, str(child_key))
    elif isinstance(value, list):
        for item in value:
            _assert_pending_safe(item, key)
    elif isinstance(value, str) and value.startswith("/"):
        raise ValueError(f"pending selection contains an absolute path in {key or 'value'}")
    elif key == "leaseFile" and not re.fullmatch(r"[a-f0-9]{64}\.lease", value):
        raise ValueError("pending selection contains an unsafe lease filename")
