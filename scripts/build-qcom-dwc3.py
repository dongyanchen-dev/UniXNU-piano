#!/usr/bin/env python3
"""Compile the SM8750 (piano) DWC3 USB controller for the native XNU kernel.

Experimental (`usb` branch). It does two things and nothing else:

  1. turn the two reviewed AppleUSBXDCI / AppleUSBXHCI fixtures into the opaque ABI
     headers the driver subclasses (the same generation the sheng port does in
     scripts/build-gop-legacy-display-27.py);
  2. compile drivers/QcomDwc3/{QcomDwc3.cpp,QcomRpmh.c} against the compile record of
     the kernel build in this tree and archive the objects as libQcomDwc3.a.

The fixtures in scripts/usb-{xdci,xhci}-24A446.json come from iPadOS 27 (24A446)
kernelcache and are arm64e pointer-authenticated. This board is iPadOS 17.7.11
(21H461) and builds an arm64 kernel, so the fixture is NOT the right one for this
kernel: it is reused only to get a compile, which is the question this branch is
asking. No diversity assertion is made here -- it would be meaningless on arm64 and
it would be false against 21H461 -- and every original address in the fixtures is a
24A446 address, so a linked driver must not be run before the fixtures are
regenerated from 21H461 (see drivers/QcomDwc3/INTEGRATION.md, section 4).

Wired in through board.toml [kernel] archives; the archive is built but not
force-loaded, so this step can only fail on the compile itself.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]          # the tree (cwd of every archive recipe)
BUILD = os.environ.get('UNIXNU_IPSW_BUILD') or '24A446'
# The reviewed fixtures are 24A446 (iPadOS 27). This device builds 21H461
# (iPadOS 17), and no fixture has been generated for it yet, so fall back to the
# reviewed set with a loud warning rather than refusing to compile at all: the
# point of this build is to prove the driver compiles and links against this
# kernel, and the vtable slot layout is what that tests. The addresses inside are
# still 24A446 addresses, so a kernel built this way must not be expected to call
# any original method correctly - regenerate the fixtures from 21H461 before
# trusting a run (drivers/QcomDwc3/INTEGRATION.md section 4).
FIXTURE = os.environ.get('UNIXNU_USB_FIXTURE') or BUILD
if not (Path(__file__).resolve().with_name(f'usb-xdci-{FIXTURE}.json')).is_file():
    FIXTURE = '24A446'
    print(f'USB: WARNING no usb-xdci-{BUILD}.json; using the 24A446 fixtures for a compile test only')
OUT = ROOT / 'build/qcom-dwc3'
OUT.mkdir(parents=True, exist_ok=True)
DEVICE = Path(os.environ.get('UNIXNU_DEVICE') or ROOT)
DRIVER = next((path for path in (DEVICE / 'drivers/QcomDwc3', ROOT / 'drivers/QcomDwc3') if path.is_dir()), None)
RECORD = ROOT / 'build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/iokit/DEVELOPMENT/IOPlatformExpert.cpo.json'
C_RECORD = ROOT / 'build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/bsd/DEVELOPMENT/kern_exec.cpo.json'


def require(value, message):
    if not value:
        raise SystemExit(message)


def run(command, **kwargs):
    print('+', ' '.join(str(v) for v in command), flush=True)
    return subprocess.run([str(v) for v in command], timeout=600, **kwargs)


def fixture(name):
    path = Path(__file__).resolve().with_name(name)
    require(path.is_file(), f'{path.name}: the reviewed ABI fixture is missing from scripts/')
    return json.loads(path.read_text())


def abi_header(abi, class_name, base_declarations, macros):
    """The opaque-storage header of one original class, exactly as the sheng port writes it."""
    methods = {int(k): v for k, v in abi['methods'].items()}
    slots = abi['slots']
    text = (f'// Generated from scripts/{abi["source"] if "source" in abi else class_name}-{BUILD}.json '
            f'(collection {BUILD}); opaque private storage only.\n#pragma once\n#include <IOKit/IOService.h>\n')
    for slot, macro in macros.items():
        require(slot in methods, f'{class_name}: slot {slot} of {macro} is not in the fixture')
        text += f'#define {macro} {methods[slot]["name"]}\n'
    text += (f'class {class_name} : public IOService {{\n OSDeclareAbstractStructors({class_name})\n'
             f' unsigned char originalPrivate[{abi["instance_size"]}-sizeof(IOService)];\npublic:\n{base_declarations}')
    for index in range(abi.get('base_slots', 168), len(slots)):
        method = methods[index]
        text += f' virtual {method["returns"]} {method["name"]}({method["parameters"]});\n'
    text += f'}};\nstatic_assert(sizeof({class_name})=={abi["instance_size"]},"Original controller instance size");\n'
    return text


XDCI_BASE = ''' void free() override;
 bool init(OSDictionary *properties=nullptr) override;
 IOReturn setProperties(OSObject *) override;
 bool start(IOService *) override;
 void stop(IOService *) override;
 bool terminate(IOOptionBits options=0) override;
 IOWorkLoop *getWorkLoop() const override;
 IOReturn callPlatformFunction(const OSSymbol *,bool,void *,void *,void *,void *) override;
 IOReturn setPowerState(unsigned long,IOService *) override;
 unsigned long maxCapabilityForDomainState(IOPMPowerFlags) override;
 unsigned long initialPowerStateForDomainState(IOPMPowerFlags) override;
 IOReturn powerStateWillChangeTo(IOPMPowerFlags,unsigned long,IOService *) override;
 IOReturn powerStateDidChangeTo(IOPMPowerFlags,unsigned long,IOService *) override;
'''

XHCI_BASE = ''' void free() override;
 bool init(OSDictionary *properties=nullptr) override;
 IOReturn setProperties(OSObject *) override;
 bool didTerminate(IOService *,IOOptionBits,bool *) override;
 void systemWillShutdown(IOOptionBits) override;
 void registerService(IOOptionBits options=0) override;
 bool start(IOService *) override;
 void stop(IOService *) override;
 bool open(IOService *,IOOptionBits options=0,void *arg=nullptr) override;
 void close(IOService *,IOOptionBits options=0) override;
 bool handleOpen(IOService *,IOOptionBits,void *) override;
 void handleClose(IOService *,IOOptionBits) override;
 bool handleIsOpen(const IOService *) const override;
 bool terminate(IOOptionBits options=0) override;
 bool matchPropertyTable(OSDictionary *,SInt32 *) override;
 bool attach(IOService *) override;
 IOWorkLoop *getWorkLoop() const override;
 IOReturn message(UInt32,IOService *,void *arg=nullptr) override;
 void PMstop() override;
 IOReturn setPowerState(unsigned long,IOService *) override;
 unsigned long maxCapabilityForDomainState(IOPMPowerFlags) override;
 unsigned long initialPowerStateForDomainState(IOPMPowerFlags) override;
 IOReturn powerStateWillChangeTo(IOPMPowerFlags,unsigned long,IOService *) override;
 IOReturn powerStateDidChangeTo(IOPMPowerFlags,unsigned long,IOService *) override;
'''

# The slots the driver overrides or calls; every other original slot stays an opaque dispatch target.
XDCI_MACROS = {179: 'XDCI_KEEP_CONFIGURATIONS', 227: 'XDCI_DESIRED_POWER', 267: 'XDCI_TRANSPORT_ACTIVE',
               268: 'XDCI_POWER_ON', 269: 'XDCI_POWER_OFF', 270: 'XDCI_PARAMETERS',
               275: 'XDCI_CONTROLLER_RESET', 277: 'XDCI_PERIODIC_USAGE', 278: 'XDCI_PERIODIC_SET'}
XHCI_MACROS = {188: 'XHCI_DESIRED_POWER', 315: 'XHCI_READ64', 317: 'XHCI_WRITE64'}

xdci = fixture(f'usb-xdci-{FIXTURE}.json')
xhci = fixture(f'usb-xhci-{FIXTURE}.json')
(OUT / 'OriginalUsbXdciABI.h').write_text(abi_header(xdci, 'AppleUSBXDCI', XDCI_BASE, XDCI_MACROS))
(OUT / 'OriginalUsbXhciABI.h').write_text(abi_header(xhci, 'AppleUSBXHCI', XHCI_BASE, XHCI_MACROS))
print(f'USB: OriginalUsbXdciABI.h ({len(xdci["slots"])} slots) and OriginalUsbXhciABI.h ({len(xhci["slots"])} slots) '
      f'from the {BUILD} fixtures')

# Only the class metadata is bound here. An original method the driver calls is left undefined on purpose: on 21H461 every
# method address must come out of its own kernelcache, so the link is where a missing entry is supposed to be visible.
bindings = {}
for abi in (xdci, xhci):
    bindings.update(abi['bindings'])
(OUT / 'usb-bindings.S').write_text('// Every address is a ' + BUILD + ' collection address: a 21H461 kernel must regenerate the fixtures.\n' +
                                    ''.join(f'.globl {name}\n.set {name}, {int(value, 16):#x}\n'
                                            for name, value in sorted(bindings.items())))
require(DRIVER is not None, 'drivers/QcomDwc3: the driver sources are not in this tree or the device repository')


def compile_source(source, destination, record_path, includes):
    """Compile one source with the kernel build's own command line, minus its warnings-as-errors flags."""
    require(record_path.is_file(), f'{record_path.relative_to(ROOT)}: no compile record (the kernel pass has not run)')
    record = json.loads(record_path.read_text().strip().rstrip(','))
    arguments, command, index = record['arguments'], [], 0
    while index < len(arguments):
        value = arguments[index]
        if value == record['file']:
            command.append(str(source))
        elif value == '-o':
            command += ['-o', str(destination)]
            index += 1
        elif value == '-Xclang' and arguments[index + 1].startswith('-W'):
            index += 1
        elif not value.startswith('-W') and value not in ('-MD', '-MP'):
            command.append(value)
        index += 1
    command += ['-Wall', '-Wextra', '-Wno-unused-parameter', '-Wno-c99-designator', '-Wno-reorder-init-list',
                '-Wno-deprecated-enum-enum-conversion', '-Wno-unnecessary-virtual-specifier',
                '-Wno-unknown-warning-option', '-I', str(OUT)]
    command += [str(value) for pair in includes for value in ('-I', pair)]
    if (ROOT / '.cache/xnu-work/osfmk').is_dir():
        command += ['-I', str(ROOT / '.cache/xnu-work/osfmk')]
    (OUT / (destination.stem + '-compile-command.json')).write_text(json.dumps(command, indent=2) + '\n')
    result = run(command, cwd=record['directory'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    (OUT / (destination.stem + '-compile.log')).write_text(result.stdout)
    if result.returncode:
        print(result.stdout, flush=True)
        raise SystemExit(f'{source.name}: the compile failed; the whole command line and its output are in '
                         f'{OUT.relative_to(ROOT)}/{destination.stem}-compile.log')
    print(f'OBJ {destination}')
    return destination


objects = [compile_source(DRIVER / 'QcomDwc3.cpp', OUT / 'QcomDwc3.o', RECORD, [DRIVER])]
run(['xcrun', 'clang', '-target', 'arm64-apple-ios17.0', '-c', OUT / 'usb-bindings.S', '-o', OUT / 'usb-bindings.o'],
    check=True)
objects.append(OUT / 'usb-bindings.o')
# The RPMh proxy votes are plain C over the AOP command database; they still compile against the kernel's C command line.
if C_RECORD.is_file():
    objects.append(compile_source(DRIVER / 'QcomRpmh.c', OUT / 'QcomRpmh.o', C_RECORD, [DRIVER]))
else:
    print(f'USB: {C_RECORD.relative_to(ROOT)} is absent; QcomRpmh.c is left to the link')
# Late registration, as every own driver in this kernel does it: the module initializer is dropped and the globalized
# function is called by the board probe instead of by dyld, which does not run for prelinked kernel code.
late = OUT / 'QcomDwc3.late.o'
run(['llvm-objcopy', '--remove-section=__DATA,__mod_init_func', '--globalize-symbol=__GLOBAL__sub_I_QcomDwc3.cpp',
     OUT / 'QcomDwc3.o', late], check=True)
objects.append(late)

archive = OUT / 'libQcomDwc3.a'
archive.unlink(missing_ok=True)
run(['xcrun', 'ar', 'rcs', archive, *objects], check=True)
(OUT / 'build-report.json').write_text(json.dumps({
    'fixture_collection': BUILD,
    'fixture_matches_this_kernel': False,
    'detail': 'usb-{xdci,xhci}-24A446.json are iPadOS 27 (24A446) arm64e fixtures; this kernel is 21H461 arm64',
    'driver_sha256': {path.name: __import__('hashlib').sha256(path.read_bytes()).hexdigest()
                      for path in (DRIVER / 'QcomDwc3.cpp', DRIVER / 'QcomRpmh.c')},
    'force_loaded': False, 'runtime_qualified': False}, indent=2) + '\n')
print(f'USB: {archive.relative_to(ROOT)} ({len(objects)} objects); fixtures are {BUILD}, this kernel is 21H461/arm64')
print('USB: built but not force-loaded; the driver is not in the kernel image of this build')
