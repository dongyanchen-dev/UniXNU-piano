#!/usr/bin/env python3
"""Validate/apply the bring-up root and RW-lock checks in an unpacked XNU tree.

The root-auth change is a normal patch in patches/xnu/series. This helper does
not rewrite bsd_init.c: it verifies that the patch preserved the autherr gate
and installed the explicit root-unverified=1 escape. The lock helper is kept
for offline reproductions of the old two-pass build; production builds use
zz-lock-rw-diagnostics.patch and invoke this script with --check.

With no --check, an unpatched lock_rw.c fixture is converted in one operation
so the five occurrences can be tested locally. A partial or ambiguous tree is
always an error; silently accepting the first occurrence was the bug this
script replaces.

usage: prepare-xnu-root-auth.py [--check] <build tree root>
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import pathlib
import re
import sys

ROOTAUTH_PANIC = 'panic("rootvp not authenticated after mounting");'
ROOTAUTH_MARKER = 'root-unverified'
ROOTAUTH_OWNER_GATE = 'if (autherr && !owner_authorized) {'

LOCKPANIC = 'panic("Taking non-sleepable RW lock with preemption enabled");'
LOCKPAT = 'if (0) ' + LOCKPANIC
LOCK_COUNT = 5
LOCK_RAW_RE = re.compile(r'(?<!if \(0\) )' + re.escape(LOCKPANIC))


def xnu_files(root: pathlib.Path, name: str):
    """Return the compiled copy only, never the untouched fetch cache.

    unixnu fetch leaves a full XNU checkout under out/feeds and patches.py
    builds from a second clone under <tree>/.cache/xnu-work.  Searching the
    whole output directory used to validate the feed copy, so --check failed
    on a correctly patched build tree.
    """
    paths = [p for p in root.rglob(name) if "xnu" in p.as_posix().lower()]
    prepared = [p for p in paths if "/xnu-work/" in p.as_posix()]
    if prepared:
        return prepared
    usable = [p for p in paths if "/out/feeds/" not in p.as_posix()]
    if paths and not usable:
        fail(f"{name} exists only in the fetch cache under {root}; "
             "run unixnu build kernel so .cache/xnu-work is prepared")
    return usable


def fail(message: str) -> "NoReturn":
    print(f"  !! {message}", file=sys.stderr)
    raise SystemExit(1)


def validate_root_auth(root: pathlib.Path) -> None:
    paths = xnu_files(root, "bsd_init.c")
    if not paths:
        fail("bsd_init.c not found under an xnu tree")
    for path in paths:
        text = path.read_text()
        if ROOTAUTH_MARKER not in text:
            fail(f"{path}: root-unverified patch marker not found")
        if ROOTAUTH_OWNER_GATE not in text or ROOTAUTH_PANIC not in text:
            fail(f"{path}: autherr/owner_authorized gate was changed or is missing")
        if 'if (0) panic("rootvp not authenticated after mounting");' in text:
            fail(f"{path}: legacy root-auth no-op is still present")
        print(f"  {path}: root-unverified patch and autherr gate present")


def apply_or_check_lock(root: pathlib.Path, check: bool) -> None:
    paths = xnu_files(root, "lock_rw.c")
    if not paths:
        fail("lock_rw.c not found under an xnu tree")
    for path in paths:
        text = path.read_text()
        raw = len(LOCK_RAW_RE.findall(text))
        already = text.count(LOCKPAT)
        if raw + already != LOCK_COUNT:
            fail(f"{path}: expected exactly {LOCK_COUNT} lock assertions, found raw={raw} patched={already}")
        if raw and already:
            fail(f"{path}: mixed patched/unpatched lock assertions")
        if check:
            if raw != LOCK_COUNT:
                fail(f"{path}: --check expects {LOCK_COUNT} original assertions")
            helper = text.count("lck_rw_non_sleepable_diagnostic")
            print(f"  {path}: {raw}/{LOCK_COUNT} assertions, {helper} diagnostic reference(s)")
            continue
        if already == LOCK_COUNT:
            print(f"  {path}: already has {LOCK_COUNT}/{LOCK_COUNT} lock no-ops")
            continue
        # Rewrite every occurrence, not just the first one. The old
        # text.replace(..., 1) silently skipped the assertion at line 1400.
        replaced, count = LOCK_RAW_RE.subn(lambda _match: LOCKPAT, text)
        if count != LOCK_COUNT or replaced.count(LOCKPAT) != LOCK_COUNT:
            fail(f"{path}: replacement count was {count}, expected exactly {LOCK_COUNT}")
        path.write_text(replaced)
        print(f"  {path}: replaced {LOCK_COUNT}/{LOCK_COUNT} lock assertions")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="validate the formal patches without rewriting sources")
    parser.add_argument("root", help="build output directory holding the fetched tree")
    args = parser.parse_args()
    root = pathlib.Path(args.root).resolve()
    if not root.is_dir():
        fail(f"build tree does not exist: {root}")
    validate_root_auth(root)
    apply_or_check_lock(root, args.check)
    return 0


if __name__ == "__main__":
    sys.exit(main())
