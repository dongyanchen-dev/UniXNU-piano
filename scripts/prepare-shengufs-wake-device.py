#!/usr/bin/env python3
"""Wake the device for level 4 (the plain adopt probe) too.

The probe reaches the LUN sweep and every logical unit answers

    L0 st=000102 ... sns=020000
    inq st=000102 ... sns=020000

which is ocs=0 (completed), scsi=2 (CHECK CONDITION) and sense key 0x02
(NOT READY): the transport works and the device is simply powered down.

ShengUfs already knows this state (its own comment: fDeviceInit = 0,
bCurrentPowerMode = 0x33 = UFS-PowerDown, every LU NOT READY) and wakes it with
START STOP UNIT, power condition ACTIVE, to the UFS Device well-known LU 0xD0 -
but only when level is 5 or 9. Level 4 is the probe this board runs, so it never
sends the wake and every command afterwards is refused.

usage: prepare-shengufs-wake-device.py <build tree root>
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import pathlib
import sys

OLD = """  if (level == 5 || level == 9) {
    query (1, 0x03, 0x02, &powerBefore, &queryResp);"""

NEW = """  // Level 4 needs the wake as well: this board's firmware leaves the device in
  // bCurrentPowerMode = 0x33 (UFS-PowerDown), so every LU answers NOT READY and
  // the LUN sweep below sees nothing but sense key 2.
  if (level == 4 || level == 5 || level == 9) {
    query (1, 0x03, 0x02, &powerBefore, &queryResp);"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="build output directory holding the fetched tree")
    args = parser.parse_args()

    patched = 0
    for path in pathlib.Path(args.root).rglob("NativeUfs.cpp"):
        if "ShengUfs" not in str(path):
            continue
        text = path.read_text()
        if "if (level == 4 || level == 5 || level == 9)" in text:
            continue
        if OLD not in text:
            print(f"  !! {path}: wake anchor not found", file=sys.stderr)
            continue
        path.write_text(text.replace(OLD, NEW, 1))
        patched += 1
        print(f"  {path}: START STOP UNIT runs for level 4 too")

    if not patched:
        print("  !! device wake not installed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())