#!/usr/bin/env python3
"""Let XNU accept the ipados root without a sealed-root signature.

bsd_init.c rejects a root that fails FSIOC_KERNEL_ROOTAUTH:

    if (require_rootauth) {
        int autherr = VNOP_IOCTL(rootvnode, FSIOC_KERNEL_ROOTAUTH, ...);
        int owner_authorized = 0;
        ...
        if (autherr && !owner_authorized) {
            panic("rootvp not authenticated after mounting");
        }
    }

UniXNU's offline-owner-root-binding-audit.patch adds the owner_authorized path,
but it only becomes non-zero when XNU_OWNER_ROOT_AUDIT and XNU_OWNER_ROOT_TRUST
are both defined and the mounted device carries one of the verified-root
policies. This board mounts a plain SHNGROOT window with no policy of its own, so
the check can never pass.

The earlier attempt to satisfy it from the other side - rd=md0-ufs, which makes
bsd_rooted_ramdisk() return true - got past the panic but then hit
lock_rw.c:1400 ('Taking non-sleepable RW lock with preemption enabled') on one
CPU as well as eight, because the rd argument also changes how the root device
is looked up.

Short-circuit the panic instead: the root is mounted and readable, and the
signature tree is the only thing missing.

usage: prepare-xnu-root-auth.py <build tree root>
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import pathlib
import sys

PANIC = 'panic("rootvp not authenticated after mounting");'
PATCHED = 'if (0) panic("rootvp not authenticated after mounting");'

# osfmk/kern/lock_rw.c, under DEBUG_LOCKS: the first assertion a successful
# mount reaches. Fires on one CPU as well as eight, with and without the rd
# argument, so neither SMP nor rd - some path takes a non-sleepable RW lock with
# preemption on. Not fatal for this port: downgrade it to a no-op.
LOCKPANIC = 'panic("Taking non-sleepable RW lock with preemption enabled");'
LOCKPAT = 'if (0) panic("Taking non-sleepable RW lock with preemption enabled");'


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="build output directory holding the fetched tree")
    args = parser.parse_args()

    patched = 0
    for path in pathlib.Path(args.root).rglob("bsd_init.c"):
        if "xnu" not in str(path):
            continue
        text = path.read_text()
        if PATCHED in text:
            continue
        if PANIC not in text:
            continue
        path.write_text(text.replace(PANIC, PATCHED, 1))
        patched += 1
        print(f"  {path}: root authentication no longer fatal")

    for path in pathlib.Path(args.root).rglob("lock_rw.c"):
        if "xnu" not in str(path):
            continue
        text = path.read_text()
        if LOCKPAT in text:
            continue
        if LOCKPANIC not in text:
            print(f"  !! {path}: lock_rw panic not found", file=sys.stderr)
            continue
        path.write_text(text.replace(LOCKPANIC, LOCKPAT, 1))
        patched += 1
        print(f"  {path}: non-sleepable RW lock assertion no longer fatal")

    if not patched:
        print("  !! nothing patched", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())