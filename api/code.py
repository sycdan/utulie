"""Crockford base32 for quids.

A label carries `HTTPS://QRGU.ID/<26 chars>`. Uppercase alphanumerics keep the
QR in alphanumeric mode, which is what lets a 128-bit id fit in a version-2
symbol -- see printer/README.md.
"""

from __future__ import annotations

import uuid

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
# Crockford folds the characters people misread when typing one off a label.
CONFUSED = {"I": "1", "L": "1", "O": "0", "U": ""}


def encode(id_: str) -> str:
    n = int(uuid.UUID(id_).hex, 16)
    return "".join(ALPHABET[(n >> (5 * i)) & 31] for i in range(26))[::-1]


def decode(code: str) -> str:
    """Back to a uuid string. Tolerates dashes, case, and misread characters."""
    cleaned = "".join(
        CONFUSED.get(c, c) for c in code.upper().replace("-", "").strip()
    )
    if not cleaned or any(c not in ALPHABET for c in cleaned):
        raise ValueError(f"{code!r} is not a quid code")
    n = 0
    for c in cleaned:
        n = n * 32 + ALPHABET.index(c)
    if n >= 1 << 128:
        raise ValueError(f"{code!r} is too long to be a quid")
    return str(uuid.UUID(int=n))
