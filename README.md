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

This tree now carries the owner-root route (`root-unverified=1`), the formal
XNU patch that preserves `autherr` while accepting that argument, and local
Piano display/input/A830 component registrations. Those owner-root and driver
changes are candidates until a new device RAM boot records the next screen or
ramoops line. The GitHub kernel and package steps link this stack (run
45338562956); payload and boot image are still unverified.

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

See [Build and boot](https://unixnu.com/building).
