# J700 single-stage KIS checkpoint

This opt-in experiment checkpoints the Aura and Linux-host code used for a
successful MacBook Neo KIS/DebugUSB proxy transaction on 2026-11-03. The build
is frozen at Aura `999b72e533449d1a9758594a9361b111b21781a0`, independently of
the surrounding checkout's revision. `default.nix` reproduces the tested raw
Aura image and the tested `kisd` executable and checks their SHA256 hashes.

The qualification covered J700/T8140, macOS firmware 26.6.2/25G83, an x86_64
Linux host, and an ordinary USB2 cable through a Steam Deck dock:

| Check | Observed result |
|---|---|
| Enumeration | `05ac:1881`, **480 Mbps**, Debug USB protocol `0400` |
| KIS binding | Descriptor base `0x348000000`, UART channel 0, FIFO free 2048 |
| Proxy identity | Chip `0x8140` and compiled-in `NEO-KIS-SINGLE-v1` tag |
| Five NOPs | All passed, 0.989–2.146 ms each |
| Watchdog command | `wdt_arm(90)` returned 0 |
| Exit | `P_EXIT` acknowledged |
| Continuation | Direct U-Boot/Linux boot with the trial's chosen properties |

## What is checkpointed

The three patch scripts preserve the tested patch stack:

1. `apply-text.py`: full-width framebuffer console, logo suppression, handoff
   checkpoints, retained final pixels, and a five-second panic-message pause.
2. `apply-single.py` / `neo-single-stage.inc.c`: strict J700 one-shot admission,
   a boot witness, direct embedded OS payload, and final watchdog cleanup.
3. `apply-kis.py` / `neo-single-kis.inc.c`: existing `hpm0` DebugUSB activation,
   a 30-second DockChannel synchronization window, clean proxy exit handling,
   and export of the result plus the last 4096 console bytes into the OS tree.

The transport, USB-device-disable guard, MMU, monitor, and chainload drivers
remain the pinned public implementations. The target-side change is the
experiment's control and diagnostics, using the existing KIS implementation.
The boot route is:

```
enrolled Stage 1 → one experimental ESP Stage 2 → original U-Boot/DTB payload → Linux
```

`patch-kisd.py` checkpoints the tested patch against
[`AsahiLinux/kisd@28608c0`](https://github.com/AsahiLinux/kisd/tree/28608c038bc994a672fb45d3aac38a4008bafbd9).
It rejects ambiguous devices and an unexpected A18 descriptor binding, allows
an owned PTY link, and provides `--once` behavior. `host-probe.py` performs the
identity/NOP/watchdog/exit transaction and captures both protocol events and
console output. All host paths are supplied as arguments.

## Build and check on x86_64 Linux

Run from this directory with Nix and its `nix-command`/`flakes` features enabled:

```sh
nix-build default.nix -A checks -o result-checks
nix-build default.nix -A reproduce -o result-reproduction
nix-build default.nix -A baseline -o result-baseline
nix-build default.nix -A stage2 -o result-stage2
nix-build default.nix -A kisd -o result-kisd
nix-build default.nix -A tools -o result-tools
```

`checks` runs the actual patched C through ASan/UBSan for admission, failure
paths, watchdog ownership, text-console lifecycle, and bounded/wrapped log
export. The `kisd` build runs its Rust descriptor and bounds tests. The complete
generated Aura source diff is `result-checks/aura.patch`.

`reproduce` checks these hardware-tested artifacts:

| Artifact | SHA256 |
|---|---|
| Baseline raw Aura | `987dbbecc4e96efc667894f8e1da01882f17d3ab727186c8ca48247afc5ef970` |
| KIS raw Aura | `efd84c750ad9b92e4fbd93c665e59aea9b42addc2342813106c0e0a061839c3f` |
| Patched `kisd` executable | `e82e7ef38c9007427e235c2af69023af125ab886df0a10d187acfc180f4b8251` |

The raw Aura footprint is 3,997,696 bytes. The tag offset is derived from the
ELF using `neo_text_stage_tag - _text_start` and verified against the raw bytes.
The hardware run used a 431,407-byte OS payload, producing a 4,429,103-byte
composed image with SHA256
`8d7e7ac42691c9bbd7ce051b1f757f806900821673883da39d5e70ad7283f95e`.

## Compose with your own working payload

Supply a copy of a known-working composed Stage 2 whose Aura prefix matches
the pinned baseline. The composer preserves every appended payload byte and
writes a new image and identity manifest into a new output directory:

```sh
result-tools/bin/python3 -B compose.py \
  --baseline result-baseline \
  --stage2 result-stage2 \
  --normal-stage2 /absolute/path/to/normal-stage2.bin \
  --output image
```

The operator's OS payload, raw firmware, ADT, RAM captures, machine identities,
SSH configuration and full hardware logs are local inputs/evidence. This
checkpoint contains source code and the summarized measured result.

## One-shot execution outline

The admitted target is **T8140, board 0x64**, boot-argument revision 3, with the
exact command line `aura-trial`. Use an enrolled Stage 1 with `aura-try` support
and a working normal fallback. The experimental image must have its own ESP
filename. `hpm0` is the rear/hinge-side connector on J700; connect that to the
Linux host. Keep the target's normal boot files and recovery path available.

On the host, use absolute paths and a new output directory. A transient
systemd unit supplies the outer process deadline and owns the PTY directory:

```sh
sudo systemd-run --unit=aura-kis-checkpoint \
  --property=RuntimeMaxSec=420 --property=TimeoutStopSec=5 \
  --property=RuntimeDirectory=aura-kis-checkpoint \
  -- /absolute/path/to/result-tools/bin/python3 -B \
  /absolute/path/to/host-probe.py \
  --source /absolute/path/to/result-stage2/share/aura/proxyclient \
  --manifest /absolute/path/to/image/manifest.json \
  --output /absolute/path/to/new-run-directory \
  --kisd /absolute/path/to/result-kisd/bin/kisd \
  --runtime /run/aura-kis-checkpoint
```

Wait for the output directory's `ready.json` before arming/rebooting the target.
The host must initially have no `05ac:1881` device; the probe refuses a stale
KIS interface. It uses its own PTY link and does not invoke `aura.setup`.

Copy `image/trial.bin` to a distinct path such as
`aurora/j700-kis-trial.bin` on the target's identified ESP, sync and verify its
hash. Select it once with the existing `aura-try` file:

```
armed
aurora/j700-kis-trial.bin
```

After reboot, Stage 1 spends that marker before loading the trial. Collect the
host's `result.json`, `events.jsonl`, `kisd.log` and console files. In Linux,
check the following properties under `/sys/firmware/devicetree/base/chosen`:

```
aurora,single-stage = NEO-KIS-SINGLE-v1
aurora,trial = <the selected experimental ESP path>
aurora,kis-window = enable=0 sync=1 session=1
aurora,kis-log = <saved pre-payload console excerpt>
```

These witnesses distinguish a direct successful continuation from a reset and
normal fallback boot. Clear the spent marker after collecting it, restore the
target's test-time sleep inhibition, and check its normal boot-file hashes and
health. The host bridge exits after the probe; collect the unit journal as well.

## Qualification boundaries

- The target arms 178 seconds before the KIS attempt. The synchronization wait
  is 30 seconds; an entered proxy session is bounded by the host process and
  watchdog, rather than a second firmware software timer.
- The target disables its trial timer before OS entry because the tested Linux
  kernel has no Apple watchdog driver. Acknowledgement of `wdt_arm(90)` is not
  proof of watchdog expiry, reset timing, or reconnect after a hang.
- The DebugUSB device remained enumerated after Linux boot. Fresh-boot versus
  stale-interface handling must be qualified before an unattended loop; this
  checkpoint deliberately refuses a pre-existing interface.
- The image tag is a build witness used with controlled device selection, not
  cryptographic authentication of a hostile USB device.
- Hardware qualification here is one successful KIS transaction and direct OS
  continuation. DCP protocol work, watchdog-expiry recovery and multi-run
  automation are subsequent experiments.

The frozen patch scripts are applied inside Nix's build sandbox. They are a
checkpoint of the tested experiment, not a production runtime option or an
unqualified rebase onto newer Aura revisions.
