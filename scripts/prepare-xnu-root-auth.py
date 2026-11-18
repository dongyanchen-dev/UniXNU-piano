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

    if not patched:
        print("  !! bsd_init.c with the root-auth panic not found", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())