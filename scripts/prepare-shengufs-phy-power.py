#!/usr/bin/env python3
"""Power the UFS PHY back up, and put both GDSCs in the panic that follows.

The tablet panics in hostBringUp with

    NATIVE_UFS adopt: TEST UNIT READY lun0
    ocs=f resp=ff scsi=ff
    hcs=00000010f->0000010f
    is=00000000 db=00000001 rsr=00000001
    pmc ok=0 gear tx/rx=0/0 lanes=0/0

HCS says the controller is ready, so the UniPro link is what went away: Gear 0
with zero lanes means the PHY is unpowered, and the doorbell is never fetched.
The firmware reads the payload from this same UFS partition through its own
UFSDxe, so the hardware is fine while the firmware owns it - UFSDxe drops
GCC_UFS_MEM_PHY_GDSC when it hands over and ShengUfs was written to adopt a
live link, never to power one.

SM8750's GDSCs are votable: SW_OVERRIDE is bit 2 and PWR_ON is bit 16.

A printf before the panic is not enough - panic clears the screen - so the two
register values travel in the panic line itself.

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
  // UFSDxe powers the PHY down when the firmware hands the controller over and
  // nothing turns it back on, so the link arrives at Gear 0: the doorbell is
  // never fetched, IS stays clear and PMC fails. Bring both GDSCs up before the
  // controller is touched; the values travel in the panic below because panic
  // clears the screen and a printf here would be lost.
  //
  {
    OSSharedPtr<IOMemoryMap> gccMap, phyMap;
    uintptr_t gcc = mapPhys (GCC_BASE + 0x77000, 0x1000, gccMap);
    uintptr_t phy = mapPhys (GCC_BASE + 0x9e000, 0x1000, phyMap);
    uint32_t ctrl = gcc ? read32 (gcc, GCC_UFS_PHY_GDSCR - 0x77000) : 0xffffffffU;
    uint32_t phyG = phy ? read32 (phy, 0) : 0xffffffffU;
    gGdscReport = ctrl;
    gPhyGdscReport = phyG;
    if (phy && phyG != 0xffffffffU && !(phyG & (1U << 16))) {
      write32 (phy, 0, (phyG | (1U << 2)) & ~1U);
      for (uint32_t spin = 0; spin < 20000; spin++) {
        if (read32 (phy, 0) & (1U << 16)) { break; }
        IODelay (10);
      }
      gPhyGdscReport = read32 (phy, 0);
    }
    if (gcc && ctrl != 0xffffffffU && !(ctrl & (1U << 16))) {
      uint32_t off = GCC_UFS_PHY_GDSCR - 0x77000;
      write32 (gcc, off, (ctrl | (1U << 2)) & ~1U);
      for (uint32_t spin = 0; spin < 20000; spin++) {
        if (read32 (gcc, off) & (1U << 16)) { break; }
        IODelay (10);
      }
      gGdscReport = read32 (gcc, off);
    }
  }
"""

DECL = """
// Reported by the level-4 panic: when the link sits at Gear 0 the PHY is the
// suspect, and panic() clears the screen so a printf before it is lost.
static uint32_t gGdscReport = 0xeeeeeeeeU, gPhyGdscReport = 0xeeeeeeeeU;"""

PANIC_OLD = """           "pmc ok=%u gear tx/rx=%u/%u lanes=%u/%u\\n"
           "rsp=%08x %08x","""

PANIC_NEW = """           "pmc ok=%u gear tx/rx=%u/%u lanes=%u/%u\\n"
           "gdsc=%08x phygdsc=%08x\\n"
           "rsp=%08x %08x","""

ARGS_OLD = """           gPmcOk, gPmcRead[0], gPmcRead[1], gPmcRead[2], gPmcRead[3],
           getBe32 (rsp0), getBe32 (rsp0 + 4));"""

ARGS_NEW = """           gPmcOk, gPmcRead[0], gPmcRead[1], gPmcRead[2], gPmcRead[3],
           gGdscReport, gPhyGdscReport,
           getBe32 (rsp0), getBe32 (rsp0 + 4));"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="build output directory holding the fetched tree")
    args = parser.parse_args()

    patched = 0
    for path in pathlib.Path(args.root).rglob("NativeUfs.cpp"):
        if "ShengUfs" not in str(path):
            continue
        text = path.read_text()
        if "gPhyGdscReport" in text:
            continue
        GLOBAL = """static UfsRootDiagnostics gRootDiagnostic;"""
        if GLOBAL not in text:
            print(f"  !! {path}: gRootDiagnostic declaration not found", file=sys.stderr)
            continue
        text = text.replace(GLOBAL, GLOBAL + DECL, 1)
        if ANCHOR not in text:
            print(f"  !! {path}: hostBringUp anchor not found", file=sys.stderr)
            continue
        text = text.replace(ANCHOR, ANCHOR + POWER, 1)
        if PANIC_OLD not in text or ARGS_OLD not in text:
            print(f"  !! {path}: panic anchor not found (run after prepare-shengufs-power-mode.py)", file=sys.stderr)
            return 1
        text = text.replace(PANIC_OLD, PANIC_NEW, 1)
        text = text.replace(ARGS_OLD, ARGS_NEW, 1)
        path.write_text(text)
        patched += 1
        print(f"  {path}: GDSC powered and reported in the panic")

    if not patched:
        print("  !! phy power not installed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())