#!/usr/bin/env python3
"""Negotiate the UFS link power mode before the first command.

Everything else about this bring-up is now correct - the takeover runs with the
firmware's own request list, at the firmware's own address, the doorbell reads
set, UTRLRSR is 1 and HCS reads 0x10F - and the first command still never
completes (ocs=f, IS clear, no fault anywhere). UPMCRS (HCS bits 10:8) is 1,
which is the device asking for a power mode change: until the host completes it
the UTP layer does not process commands at all.

Mainline does this in ufshcd_dme_change_power_mode(): read the gear and lane
count the link is on, write them back, and finish with DME_SET(PA_PWRMODE).

Sequence, from ufshcd.c:

    DME_SET PA_RXGEAR              gear_rx
    DME_SET PA_ACTIVERXDATALANES   lane_rx
    DME_SET PA_RXTERMINATION       1  (FAST modes only)
    DME_SET PA_TXGEAR              gear_tx
    DME_SET PA_ACTIVETXDATALANES   lane_tx
    DME_SET PA_TXTERMINATION       1
    DME_SET PA_HSSERIES            rate (2 = B)
    DME_SET PA_PWRMODE             (pwr_rx << 4) | pwr_tx, FAST_MODE = 1

MIB numbers and the PWRMODE encoding come from include/ufs/unipro.h:

    PA_ACTIVETXDATALANES  0x1560   PA_TXGEAR    0x1568
    PA_TXTERMINATION      0x1569   PA_HSSERIES  0x156A
    PA_PWRMODE            0x1571   PA_ACTIVERXDATALANES 0x1580
    PA_RXGEAR             0x1583   PA_RXTERMINATION     0x1584

UIC command layout: UCMDARG1 = idn << 16 (UIC_ARG_MIB), UCMDARG3 carries the
value for DME_SET, UCMDARG2 carries the result. Completion is IS bit 10
(UIC_COMMAND_COMPL); the result is ARG2 bits 7:0.

The measured values are reported through the level-4 panic that already exists,
so nothing new has to be printed and no new call is introduced.

usage: prepare-shengufs-power-mode.py <build tree root>
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import pathlib
import sys

MARKER = "ufsPowerModeChange"

HELPERS = """// UFS link power mode change, the step every other UFS host does before the
// first command: while UPMCRS (HCS bits 10:8) is set the UTP does not process
// anything, so the doorbell reads set, IS stays clear and ocs stays 0xf.
// Mainline: ufshcd_dme_change_power_mode() in drivers/ufs/core/ufshcd.c.
static uint32_t gPmcRead[4] = { 0xFF, 0xFF, 0xFF, 0xFF };   // tx gear, rx gear, tx lanes, rx lanes
static uint32_t gPmcOk;                                     // 1 when the reads and writes all landed

static bool uicMib (uintptr_t hc, uint32_t opcode, uint32_t idn, uint32_t value, uint32_t *out)
{
  write32 (hc, 0x48, 0);
  write32 (hc, 0x4C, value);
  write32 (hc, 0x44, idn << 16);          // UIC_ARG_MIB(idn)
  write32 (hc, 0x20, 0x400);              // clear UIC_COMMAND_COMPL
  write32 (hc, 0x40, opcode);             // 1 = DME_GET, 2 = DME_SET
  for (unsigned spin = 0; spin < 100000; spin++) {
    if (read32 (hc, 0x20) & 0x400) break;
    IODelay (10);
  }
  uint32_t is = read32 (hc, 0x20), arg2 = read32 (hc, 0x48), arg3 = read32 (hc, 0x4C);
  write32 (hc, 0x20, 0x400);
  if (out) *out = arg3;
  return ((is & 0x400) != 0) && ((arg2 & 0xFF) == 0);
}

static void ufsPowerModeChange (uintptr_t hc)
{
  uint32_t txGear = 0, rxGear = 0, txLanes = 0, rxLanes = 0;
  bool ok = true;

  ok &= uicMib (hc, 1, 0x1568, 0, &txGear);     // PA_TXGEAR
  ok &= uicMib (hc, 1, 0x1583, 0, &rxGear);     // PA_RXGEAR
  ok &= uicMib (hc, 1, 0x1560, 0, &txLanes);    // PA_ACTIVETXDATALANES
  ok &= uicMib (hc, 1, 0x1580, 0, &rxLanes);    // PA_ACTIVERXDATALANES

  gPmcRead[0] = txGear; gPmcRead[1] = rxGear; gPmcRead[2] = txLanes; gPmcRead[3] = rxLanes;

  if (!ok || (txGear == 0) || (rxGear == 0) || (txLanes == 0) || (rxLanes == 0)) {
    // Nothing readable: ask for the slowest mode the spec allows rather than
    // guessing at a gear the link may not support. PWM-G1, one lane, slow.
    txGear = 1; rxGear = 1; txLanes = 1; rxLanes = 1;
    gPmcOk = 0;
  } else {
    gPmcOk = 1;
  }

  uicMib (hc, 2, 0x1583, rxGear, nullptr);      // PA_RXGEAR
  uicMib (hc, 2, 0x1580, rxLanes, nullptr);     // PA_ACTIVERXDATALANES
  uicMib (hc, 2, 0x1584, 1, nullptr);           // PA_RXTERMINATION
  uicMib (hc, 2, 0x1568, txGear, nullptr);      // PA_TXGEAR
  uicMib (hc, 2, 0x1560, txLanes, nullptr);     // PA_ACTIVETXDATALANES
  uicMib (hc, 2, 0x1569, 1, nullptr);           // PA_TXTERMINATION
  uicMib (hc, 2, 0x156A, 2, nullptr);           // PA_HSSERIES: rate B
  uicMib (hc, 2, 0x1571, (1U << 4) | 1U, nullptr);   // PA_PWRMODE: FAST rx, FAST tx
}

"""

ANCHOR = "  uint32_t powerBefore = 0, powerAfter = 0, queryResp = 0, ignoredValue = 0;"

CALL = """  // Complete the power mode change the device has been asking for; the UTP
  // does not process commands until it is done.
  ufsPowerModeChange (hc);

"""

PANIC_OLD = """           "is=%08x db=%08x rsr=%08x\\n"
           "rsp=%08x %08x",
           t.ocs, t.response, t.scsi, phys, hcsBefore, read32 (hc, 0x30), smmuReport[0], smmuReport[1],
           read32 (hc, 0x20), read32 (hc, 0x58), read32 (hc, 0x60), getBe32 (rsp0), getBe32 (rsp0 + 4));"""

PANIC_NEW = """           "is=%08x db=%08x rsr=%08x\\n"
           "pmc ok=%u gear tx/rx=%u/%u lanes=%u/%u\\n"
           "rsp=%08x %08x",
           t.ocs, t.response, t.scsi, phys, hcsBefore, read32 (hc, 0x30), smmuReport[0], smmuReport[1],
           read32 (hc, 0x20), read32 (hc, 0x58), read32 (hc, 0x60),
           gPmcOk, gPmcRead[0], gPmcRead[1], gPmcRead[2], gPmcRead[3],
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
        if MARKER in text:
            print(f"  {path}: already patched")
            patched += 1
            continue
        if ANCHOR not in text:
            print(f"  !! {path}: adopt command anchor not found", file=sys.stderr)
            continue
        text = text.replace(ANCHOR, CALL + ANCHOR, 1)
        if PANIC_OLD not in text:
            print(f"  !! {path}: level-4 panic not found", file=sys.stderr)
            continue
        text = text.replace(PANIC_OLD, PANIC_NEW, 1)
        # Helpers go before the class definition so adoptAndRead can call them.
        # After read32()/write32(), before anything that uses them.
        hook = "static bool contains (const char *data, size_t length, const char *needle)\n"
        if hook not in text:
            print(f"  !! {path}: global anchor not found", file=sys.stderr)
            continue
        text = text.replace(hook, HELPERS + hook, 1)
        path.write_text(text)
        patched += 1
        print(f"  {path}: link power mode change added before the first command")

    if not patched:
        print("  !! NativeUfs.cpp not found", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
