"""Literal redaction for sensitive SQL.

Replaces string literals, numeric literals, and IN-list contents with
placeholders. Preserves SQL structure and identifiers — lineage is unchanged
because lineage depends on identifiers, not values.

Caveats (documented in docs/known-limitations.md):
- A literal that participates in a `WHERE col = literal` filter and is then
  used in an aggregation may have lower confidence after redaction because
  the parser cannot fold the constant.
- Date/timestamp literals are redacted too — if the parser used them for
  filter elimination, the lineage may broaden (more upstream columns reported).
- Identifier-quoting (`backtick`, `[bracket]`, `"double"`) is preserved.
"""

from __future__ import annotations

import re

# Order matters: handle quoted identifiers first so we don't redact their content.
_QUOTED_IDENT = re.compile(r'(`[^`]*`|"[^"]*"|\[[^\]]*\])')
_STRING_LITERAL = re.compile(r"'(?:\\'|[^'])*'")
_NUMERIC_LITERAL = re.compile(r"\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b")


def redact(sql: str) -> str:
    """Replace literals with placeholders. Returns the redacted SQL."""
    placeholders: list[str] = []

    # Stash quoted identifiers so we don't touch their inner content.
    def _stash_ident(m: re.Match) -> str:
        placeholders.append(m.group(0))
        return f"\x00IDENT{len(placeholders) - 1}\x00"

    s = _QUOTED_IDENT.sub(_stash_ident, sql)
    s = _STRING_LITERAL.sub("'<REDACTED>'", s)
    s = _NUMERIC_LITERAL.sub("0", s)

    # Restore identifiers.
    for i, ident in enumerate(placeholders):
        s = s.replace(f"\x00IDENT{i}\x00", ident)
    return s
