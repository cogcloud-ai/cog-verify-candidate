#!/usr/bin/env python3
"""Check requirements.txt against requirements.in and PyPI's published hashes.

Recompiling over the committed lock is not enough: `uv pip compile -o` reads
the existing output file and keeps its hashes, so a corrupted or substituted
hash survives the recompile. This check instead keeps only the committed
versions, as constraints, and compiles into a fresh file, so every hash comes
from the package index. It fails if the result differs from the committed lock,
which catches hashes that don't match PyPI's for the pinned versions (changed,
added or removed), a pin that no longer satisfies requirements.in, and a
package added to or removed from requirements.in without regenerating the lock.

It does not check which versions are pinned: a lock moved to another real
release that still satisfies requirements.in, such as an older transitive
dependency, passes with that release's genuine hashes. Review version changes
in the lock's diff.

Run from the repository root, with uv 0.13.5 or newer on PATH:

    python3 isolation/check_lock.py [--lock PATH] [--self-test]

--self-test also confirms that the check rejects a copy of the lock with one
hash substituted, so the check itself cannot silently stop working.
"""

import argparse
import difflib
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Keep in step with the command in the header of requirements.txt.
COMPILE_ARGS = ["--universal", "--python-version", "3.11", "--generate-hashes"]
PIN = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)==(?P<version>[^\s;\\]+)"
    r"(?P<marker>\s*;[^\\]*)?"
)
HASH = re.compile(r"--hash=sha256:[0-9a-f]{64}")


class LockError(Exception):
    pass


def requirement_lines(text):
    """Requirement and hash lines without comments, blank lines or the
    trailing continuation backslashes, for a format-independent comparison."""
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(stripped.rstrip("\\").rstrip())
    return lines


def pins(text):
    """The committed `name==version ; marker` lines, as constraints."""
    found = []
    for line in text.splitlines():
        match = PIN.match(line)
        if match:
            found.append(
                f"{match['name']}=={match['version']}{(match['marker'] or '').rstrip()}"
            )
    return found


def recompile(committed, input_path):
    """Compile requirements.in with the committed versions as constraints, into
    a new file, so uv takes every hash from the index, not from the lock."""
    constraints = pins(committed)
    if not constraints:
        raise LockError("no pinned requirements found in the lock")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "constraints.txt").write_text(
            "\n".join(constraints) + "\n", encoding="utf-8"
        )
        fresh_path = tmp / "requirements.txt"  # new file: no hashes to reuse
        try:
            result = subprocess.run(
                [
                    "uv",
                    "pip",
                    "compile",
                    str(input_path),
                    *COMPILE_ARGS,
                    "--no-header",
                    "--no-annotate",
                    "--quiet",
                    "--refresh",
                    "--constraint",
                    str(tmp / "constraints.txt"),
                    "--output-file",
                    str(fresh_path),
                ],
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            raise LockError(
                "uv was not found on PATH; install uv 0.13.5 or newer"
            ) from None
        if result.returncode:
            raise LockError(
                "could not recompile the committed versions; check "
                "that they still satisfy requirements.in:\n" + result.stderr
            )
        return fresh_path.read_text(encoding="utf-8")


def differences(committed, input_path, label):
    """A unified diff from the committed lock to the recompiled one, or []."""
    want = requirement_lines(recompile(committed, input_path))
    have = requirement_lines(committed)
    return list(
        difflib.unified_diff(
            [line + "\n" for line in have],
            [line + "\n" for line in want],
            fromfile=f"{label} (committed)",
            tofile="recompiled from requirements.in and PyPI",
        )
    )


def self_test(committed, input_path):
    """The check must reject the lock with its first hash substituted."""
    first = HASH.search(committed)
    if first is None:
        raise LockError("self-test: the lock has no hashes to substitute")
    tampered = committed.replace(first.group(), "--hash=sha256:" + "0" * 64, 1)
    if not differences(tampered, input_path, "tampered lock"):
        raise LockError(
            "self-test: a substituted hash was NOT detected; the check no longer works"
        )
    print("self-test: a substituted hash is detected")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--lock", type=Path, default=HERE / "requirements.txt")
    parser.add_argument("--input", type=Path, default=HERE / "requirements.in")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="also confirm a substituted hash is detected",
    )
    args = parser.parse_args()

    committed = args.lock.read_text(encoding="utf-8")
    try:
        diff = differences(committed, args.input, str(args.lock))
        if diff:
            sys.stdout.writelines(diff)
            raise LockError(
                "the lock does not match requirements.in and "
                "PyPI's hashes; regenerate it with the command in "
                "its header"
            )
        print(
            f"{args.lock}: {len(pins(committed))} pins and "
            f"{len(HASH.findall(committed))} hashes match requirements.in "
            f"and PyPI"
        )
        if args.self_test:
            self_test(committed, args.input)
    except LockError as exc:
        sys.exit(f"error: {exc}")


if __name__ == "__main__":
    main()
