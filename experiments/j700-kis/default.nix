# Frozen, opt-in reproduction of the hardware-tested J700 KIS experiment.
let
  hostNixpkgs = builtins.fetchTree {
    type = "tarball";
    url = "https://releases.nixos.org/nixos/unstable/nixos-26.11pre1103272.31ecbaca1bde/nixexprs.tar.zst";
    narHash = "sha256-yXRSdZdZZqccEL+j11lc1gFG1f7V5j8N7oPBTHwf7n4=";
  };
  targetNixpkgs = builtins.fetchTree {
    type = "github";
    owner = "NixOS";
    repo = "nixpkgs";
    rev = "ec2d622de0773551768cf98f3fc50cbcc003b9c5";
    narHash = "sha256-Ue1Yo8gfHdD4TMtNewhA4tkSYeFqXThju0nCyJc3ALo=";
  };
  pkgs = import hostNixpkgs { system = "x86_64-linux"; };
  buildPkgs = import targetNixpkgs { system = "x86_64-linux"; };
  source = builtins.fetchTree {
    type = "github";
    owner = "aurora-silicon";
    repo = "aura";
    rev = "999b72e533449d1a9758594a9361b111b21781a0";
    narHash = "sha256-S7A0LQmbGypP8LagmFzKR3+nNhtBfrnrbxDzdLSqOQI=";
  };
  files = builtins.path {
    path = ./.;
    name = "j700-kis-checkpoint-source";
    filter = path: type: type == "regular" && builtins.elem (baseNameOf path) [
      "apply-text.py" "apply-single.py" "apply-kis.py"
      "neo-single-stage.inc.c" "neo-single-kis.inc.c"
      "test-text.py" "test-single.c" "test-kis.c"
    ];
  };
  applyTrial = ''
    ${pkgs.python3}/bin/python3 -B ${files}/apply-text.py . --label NEO-TEXT-RETURN-v1
    ${pkgs.python3}/bin/python3 -B ${files}/apply-single.py .
    ${pkgs.python3}/bin/python3 -B ${files}/apply-kis.py .
  '';
  checks = pkgs.runCommand "j700-kis-checkpoint-checks" {
    nativeBuildInputs = [ pkgs.python3 pkgs.stdenv.cc ];
  } ''
    mkdir -p $out/text $out/single $out/kis
    cp -r ${source} source
    chmod -R u+w source
    pushd source
    ${applyTrial}
    popd
    for file in usb.c usb_cdc.c tps6598x.c dockchannel_uart.c uartproxy.c chainload.c monitor.c memory.c; do
      cmp source/src/$file ${source}/src/$file
    done
    python3 -B ${files}/test-text.py source $out/text
    for test in single kis; do
      # Quoted includes must resolve to the patched C, not the checkpoint inputs.
      cp ${files}/test-$test.c $out/$test/test-$test.c
      cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
        -I source/src $out/$test/test-$test.c -o $out/$test/actual-$test
      $out/$test/actual-$test > $out/$test/stdout.txt
    done
    for file in Makefile src/main.c src/fb.c src/utils.c; do
      diff -u --label a/$file --label b/$file ${source}/$file source/$file >> $out/aura.patch || test $? -eq 1
    done
    for file in src/neo-single-stage.inc.c src/neo-single-kis.inc.c; do
      diff -u --label /dev/null --label b/$file /dev/null source/$file >> $out/aura.patch || test $? -eq 1
    done
    touch $out/passed
  '';
  baseM1n1 = buildPkgs.pkgsCross.aarch64-multiplatform.m1n1.override { customLogo = null; };
  cargoDeps = baseM1n1.rustPlatform.fetchCargoVendor {
    src = "${source}/rust";
    sourceRoot = "rust";
    hash = "sha256-Rw9xhDAZx1YIiS62fKmSoq8FDZ1JJNhA7p/Wx35R7RQ=";
  };
  baseline = baseM1n1.overrideAttrs (old: {
    pname = "neo-aura29-esp-stage2";
    version = "999b72e53344";
    src = source;
    inherit cargoDeps;
    makeFlags = old.makeFlags ++ [ "ESP_STAGE2=1" "BUILTIN_LOGO=aurora" "VERSION=aura-999b72e53344" ];
    nativeBuildInputs = old.nativeBuildInputs ++ [ buildPkgs.python3 ];
    installPhase = ''
      runHook preInstall
      mkdir -p $out/lib/aura $out/share/aura
      cp build/aura.bin build/aura.elf build/aura-boot.macho $out/lib/aura/
      cp -r tools docs proxyclient LICENSE LICENSES 3rdparty_licenses $out/share/aura/
      cp build/build_cfg.h build/build_tag.h $out/share/aura/
      runHook postInstall
    '';
  });
  stage2 = baseline.overrideAttrs (old: {
    pname = "neo-single-kis-trial";
    postPatch = (old.postPatch or "") + ''
      test -f ${checks}/passed
      ${applyTrial}
    '';
  });
  kisSource = builtins.fetchTree {
    type = "github";
    owner = "AsahiLinux";
    repo = "kisd";
    rev = "28608c038bc994a672fb45d3aac38a4008bafbd9";
  };
  kisd = pkgs.rustPlatform.buildRustPackage {
    pname = "neo-kisd";
    version = "1.1.0-28608c0";
    src = kisSource;
    cargoLock.lockFile = "${kisSource}/Cargo.lock";
    postPatch = ''${pkgs.python3}/bin/python3 -B ${./patch-kisd.py} .'';
    nativeBuildInputs = [ pkgs.pkg-config ];
    buildInputs = [ pkgs.udev ];
    doCheck = true;
    doInstallCheck = true;
    installCheckPhase = ''
      $out/bin/kisd --help > $out/help.txt
      $out/bin/kisd --version
    '';
  };
  tools = pkgs.python3.withPackages (p: [ p.pyserial p.construct p.pyelftools ]);
  reproduce = pkgs.runCommand "j700-kis-tested-binary-reproduction" { } ''
    test "$(sha256sum ${baseline}/lib/aura/aura.bin | cut -d ' ' -f 1)" = 987dbbecc4e96efc667894f8e1da01882f17d3ab727186c8ca48247afc5ef970
    test "$(sha256sum ${stage2}/lib/aura/aura.bin | cut -d ' ' -f 1)" = efd84c750ad9b92e4fbd93c665e59aea9b42addc2342813106c0e0a061839c3f
    test "$(sha256sum ${kisd}/bin/kisd | cut -d ' ' -f 1)" = e82e7ef38c9007427e235c2af69023af125ab886df0a10d187acfc180f4b8251
    mkdir $out
    sha256sum ${baseline}/lib/aura/aura.bin ${stage2}/lib/aura/aura.bin ${kisd}/bin/kisd > $out/SHA256SUMS
    touch $out/passed
  '';
in { inherit baseline stage2 checks kisd tools reproduce; }
