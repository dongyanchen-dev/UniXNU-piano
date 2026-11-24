# UniXNU for the Xiaomi Pad 8 Pro (piano)

| | |
| --- | --- |
| What | [UniXNU](https://github.com/UniXNU/UniXNU) device repository: runs iPadOS on the Pad 8 Pro (SM8750) |
| Goes | Next to a `UniXNU` checkout, as `-D ../android_device_xiaomi_piano-unixnu` |
| Comes from | The UniXNU device template, with the SM8750 support of the OnePlus 13T port ([UniXNU-sm8750-common](https://github.com/IssacL04/UniXNU-sm8750-common)) |
| Firmware | A Mu-Silicium based UEFI build; run its `tools/setup-deps.sh`, then build with `--uefi` pointing at its `deps/Mu-Silicium` (see `[firmware]` in `board.toml`) |
| OS | iPadOS 17.7.11 (21H461) |

## State

The last device-verified image was a RAM boot (`fastboot boot`, with no
partition written). ShengUfs read the GPT and the SHNGROOT window beginning at
LBA `55778816`; APFS volume `04769D26-2CA0-4825-B443-E2E5F88300F2` mounted as
root. The boot then stopped at the first `DEBUG_LOCKS` assertion in
`lock_rw.c:1400`, `Taking non-sleepable RW lock with preemption enabled`.

This tree carries the owner-root route as series patches: `root-unverified=1`
with `zzz-root-unverified.patch` keeping the `autherr` gate, the five-site
`lock_rw` backtrace diagnostic, `initproc-no-panic=1` with its `kern_exit.c`
patch, the SystemOS volume retry, and the local Piano display/input/A830
component registrations. All of them are candidates until a device RAM boot
records the next line.

The workflow builds and packages the stack. Run `45396130152` (commit `97f9534`)
is the first green build with the USB console: the kernel step now asserts that
the linked `mach.development.bcm2837.unstripped.noctf` defines
`piano_usb_console_start`, and it reported `assertions=5 diagnostics=6` for the
prepared `lock_rw.c`. Run `45342205030` uploaded the 156 MB `piano-ipados-17`
artifact, and run `45399823289` (commit `6a1dde2`) adds `initproc-no-panic` and
the SystemOS volume retry and uploaded `piano-ipados-17` again (artifact
`14924936205`, 163,584,503 bytes,
`sha256:6972c11fd5df2a529b3ba6a315a9136ed5cbd3a19343f134a614df34ce0d0a30`). No
device boot has used any of these images yet.

`panic_screen` is off in this revision. `BootProgress.c` paints the panic
message and registers itself, while the Enc3l entry probe refuses the image
because its fixed `SCTLR/ISB/CPACR` signature no longer matches this kernel's
early-progress and bootstrap-table patches. The USB payload path remains the transport for this revision:
the pinned Enc3l `bootimg.py` does implement `embed_payload`, but the pinned
piano UEFI branch has no `PianoPayloadDxe`, so nothing would point `/chosen
initrd` at the embedded bytes yet.

The storage ids in this revision are the local Piano sources (`NativeUfs`,
`NativeVirtioBlock`, `NativeRamBlock`, `PaganiVerifiedRoot`) rather than the
official `ShengUfs`/`VirtioMmioBlock`/`RamBlock`/`VerifiedRoot`: the official
`ShengUfs` does not export the `native_ufs_log_*` entry points that
`BootProgress`'s `UfsLog.o` calls, and `VirtioMmioBlock` without
`--verified-root` compiled out the `native_verified_block_*` functions, so the
kernel link failed. That swap is a build-side candidate; no device boot has
used it yet. No partition is flashed; the host stages
`payload.img` with `fastboot stage`/`fastboot oem ramdisk`.

## Build

Needs macOS with Xcode. From the UniXNU checkout:

```sh
./unixnu defconfig piano_defconfig -D ../android_device_xiaomi_piano-unixnu
./unixnu fetch
./unixnu build kernel
./unixnu build package
./unixnu build firmware --uefi ../uefi/deps/Mu-Silicium
./unixnu build payload
./unixnu bootimg
fastboot boot <output>/boot/boot.img
# Current firmware transport (boot manager waits for the staged payload):
fastboot stage <output>/payload/payload.img
fastboot oem ramdisk
```

## Watching the boot

`scripts/PianoUsbConsole.c` starts from `bsd_init` (patched in by
`patches/xnu/piano-usb-console.patch`) and presents the SM8750 DWC3 as one
CDC-ACM port, VID `0x1209` / PID `0x0001`. Everything the kernel prints is
copied to it while the host keeps the port open, so the boot no longer has to
be read off the panel:

- macOS: `/dev/cu.usbmodem*` (`screen /dev/cu.usbmodemXXXX 115200`)
- Windows: a `COMx` port (PuTTY, or `putty -serial COMx`)
- Linux: `/dev/ttyACM*`

Open it before the payload boots. If the boot stops at `lock_rw.c:1400`, the
diagnostic patch prints `Taking non-sleepable RW lock at <function>:<line>`
and the eight caller frames that follow are the answer to which path took a
non-sleepable lock with preemption enabled.

See [Build and boot](https://unixnu.com/building).
