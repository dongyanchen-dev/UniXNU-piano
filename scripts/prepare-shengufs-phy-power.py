#!/usr/bin/env python3
"""Power the UFS PHY back up before the kernel takes the controller over.

The tablet panics in hostBringUp with

    NATIVE_UFS adopt: TEST UNIT READY lun0
    ocs=f resp=ff scsi=ff
    hcs=00000010f->0000010f
    is=00000000 db=00000001 rsr=00000001
    pmc ok=0 gear tx/rx=0/0 lanes=0/0

The controller reports ready (HCS low nibble 0xf) but the UniPro link sits at
Gear 0 with zero lanes, so the doorbell is never fetched. The firmware reads
the payload from the very same UFS partition (its own UFSDxe installs two
DiskIo handles), so the hardware is fine while the firmware owns it: what is
missing is the PHY after hand-over. UFSDxe drops GCC_UFS_MEM_PHY_GDSC when it
stops, and nothing in ShengUfs turns it back on - the driver assumes it adopts
a live link.

SM8750's GDSCs are votable: SW_OVERRIDE is bit 2 (not bit 1) and PWR_ON is
bit 16 (not bit 31). Report both GDSCs, then bring them up and poll for PWR_ON,
so the next boot says whether the PHY was the missing piece.

usage: prepare-shengufs-phy-power.py <build tree root>
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import pathlib
import sys

ANCHOR = """static bool hostBringUp (const char **why)
{
  if (gHost.poisoned) {
    *why = "transport quarantined";
    return false;
  }
"""

POWER = """  //
  // UFSDxe powers the PHY down when the firmware hands the controller over, and
  // nothing turns it back on, so the link arrives at Gear 0 and every command
  // times out (db stays set, IS stays clear, pmc fails). Bring both GDSCs up
  // before touching the controller, and print them either way so a boot states
  // whether that was the missing piece.
  //
  {
    OSSharedPtr<IOMemoryMap> gccMap, phyMap;
    uintptr_t gcc = mapPhys (GCC_BASE + 0x77000, 0x1000, gccMap);
    uintptr_t phy = mapPhys (GCC_BASE + 0x9e000, 0x1000, phyMap);
    uint32_t ctrl = gcc ? read32 (gcc, GCC_UFS_PHY_GDSCR - 0x77000) : 0xffffffffU;
    uint32_t phyG = phy ? read32 (phy, 0) : 0xffffffffU;
    printf ("NATIVE_UFS phy: gdsc=%08x phygdsc=%08x\\n", ctrl, phyG);
    // SM8750 GDSCs are votable: bit2 SW_OVERRIDE, bit0 SW_COLLAPSE, bit16 PWR_ON.
    if (phy && phyG != 0xffffffffU && !(phyG & (1U << 16))) {
      write32 (phy, 0, (phyG | (1U << 2)) & ~1U);
      for (uint32_t spin = 0; spin < 20000; spin++) {
        if (read32 (phy, 0) & (1U << 16)) { break; }
        IODelay (10);
      }
      printf ("NATIVE_UFS phy: phygdsc after=%08x\\n", read32 (phy, 0));
    }
    if (gcc && ctrl != 0xffffffffU && !(ctrl & (1U << 16))) {
      uint32_t off = GCC_UFS_PHY_GDSCR - 0x77000;
      write32 (gcc, off, (ctrl | (1U << 2)) & ~1U);
      for (uint32_t spin = 0; spin < 20000; spin++) {
        if (read32 (gcc, off) & (1U << 16)) { break; }
        IODelay (10);
      }
      printf ("NATIVE_UFS phy: gdsc after=%08x\\n", read32 (gcc, off));
    }
  }
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="build output directory holding the fetched tree")
    args = parser.parse_args()

    patched = 0
    for path in pathlib.Path(args.root).rglob("NativeUfs.cpp"):
        if "ShengUfs" not in str(path):
            continue
        text = path.read_text()
        if "NATIVE_UFS phy: gdsc=" in text:
            continue
        if ANCHOR not in text:
            print(f"  !! {path}: anchor not found", file=sys.stderr)
            continue
        path.write_text(text.replace(ANCHOR, ANCHOR + POWER, 1))
        patched += 1
        print(f"  {path}: GDSC reported and powered before bring-up")

    if not patched:
        print("  !! phy power not installed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())