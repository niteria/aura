"""Compose the frozen KIS image with an operator-supplied working OS payload."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from elftools.elf.elffile import ELFFile

BASELINE_SHA256 = "987dbbecc4e96efc667894f8e1da01882f17d3ab727186c8ca48247afc5ef970"
TRIAL_SHA256 = "efd84c750ad9b92e4fbd93c665e59aea9b42addc2342813106c0e0a061839c3f"
TAG = "NEO-KIS-SINGLE-v1"


def compose(baseline, stage2, normal_path, output):
    original = (baseline / "lib/aura/aura.bin").read_bytes()
    raw = (stage2 / "lib/aura/aura.bin").read_bytes()
    normal = normal_path.read_bytes()
    if hashlib.sha256(original).hexdigest() != BASELINE_SHA256:
        raise ValueError("baseline does not match the frozen tested Aura build")
    if hashlib.sha256(raw).hexdigest() != TRIAL_SHA256:
        raise ValueError("trial does not match the frozen tested KIS build")
    if not normal.startswith(original) or len(normal) <= len(original):
        raise ValueError("normal Stage 2 must contain the exact baseline prefix and an OS payload")
    payload = normal[len(original):]
    magic, version, flags, footprint, run_base = struct.unpack_from("<QIIQQ", raw, 0x808)
    if not (magic == 0x44414F4C41525541 and version == 1 and flags & 1 and run_base == 0
            and footprint == len(raw) and footprint % 16384 == 0):
        raise ValueError("unexpected raw Aura chainload header")
    with (stage2 / "lib/aura/aura.elf").open("rb") as handle:
        symbols = {symbol.name: symbol["st_value"]
                   for symbol in ELFFile(handle).get_section_by_name(".symtab").iter_symbols()}
    offset = symbols["neo_text_stage_tag"] - symbols["_text_start"]
    tag_bytes = TAG.encode() + b"\0"
    if not (0 < offset < footprint - len(tag_bytes)
            and raw[offset:offset + len(tag_bytes)] == tag_bytes):
        raise ValueError("ELF/raw-image trial identity mismatch")
    config = (stage2 / "share/aura/build_cfg.h").read_text()
    for name in ("ESP_STAGE2", "NEO_TEXT_CONSOLE", "NEO_SINGLE_STAGE", "NEO_SINGLE_KIS"):
        if "#define " + name + "\n" not in config:
            raise ValueError("missing build option: " + name)
    if "NEO_CDC_TRIAL" in config:
        raise ValueError("unexpected CDC experiment in the KIS image")
    image = raw + payload
    manifest = dict(
        source_revision="999b72e533449d1a9758594a9361b111b21781a0",
        raw_sha256=hashlib.sha256(raw).hexdigest(), raw_size=len(raw), footprint=footprint,
        tag=TAG, tag_hex=tag_bytes.hex(), tag_offset=offset, config=config,
        normal_sha256=hashlib.sha256(normal).hexdigest(),
        image_sha256=hashlib.sha256(image).hexdigest(), image_size=len(image),
        payload_sha256=hashlib.sha256(payload).hexdigest(), payload_bytes=len(payload),
        payload_byte_exact=True, extra_aura_hops=0, window_ms=30000,
        transport="KIS/DebugUSB", usb_vid_pid="05ac:1881", uart_channel=0,
        kisd_revision="28608c038bc994a672fb45d3aac38a4008bafbd9",
        kisd_expected_descriptor_base="0x348000000",
    )
    output.mkdir(exist_ok=False)
    with (output / "trial.bin").open("xb") as handle:
        handle.write(image)
    with (output / "manifest.json").open("x") as handle:
        json.dump(manifest, handle, indent=2)
        handle.write("\n")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--stage2", type=Path, required=True)
    parser.add_argument("--normal-stage2", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest = compose(args.baseline, args.stage2, args.normal_stage2, args.output)
    except (OSError, ValueError, KeyError, struct.error) as error:
        parser.error(str(error))
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
