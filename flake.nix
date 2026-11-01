{
  description = "dov-bot: custom ArtBOT for Dov (The Bear) — Google L6 TPM, Linear Board Auditor, Velocity Forecaster, and 0-to-5 Bear Alarm Protocol";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/0954f7ee2f6bb3dc7d4e3d0d8bcb8fd4bde4cfc5";
    shac-src = {
      url = "github:shac-project/shac/63c0571f70f71c533d5ce623fb30a4d8813f24af";
      flake = false;
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      shac-src,
    }:
    let
      inherit (nixpkgs) lib;
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      forAllSystems = f: lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});

      shacFor = pkgs: pkgs.callPackage ./nix/shac.nix { src = shac-src; };

      pythonFor =
        pkgs:
        pkgs.python3.withPackages (
          ps: with ps; [
            pyyaml
            pytest
            pytest-cov
            pytest-bdd
            pytest-randomly
            mypy
            types-pyyaml
          ]
        );

      devTools =
        pkgs: with pkgs; [
          (shacFor pkgs)
          (pythonFor pkgs)
          ruff
          nixfmt
          statix
          deadnix
          yamllint
          just
          git
        ];

      mkCheck =
        pkgs: name: script:
        pkgs.runCommand "check-${name}"
          {
            nativeBuildInputs = devTools pkgs;
          }
          ''
            cp -r ${self} src
            chmod -R u+w src
            cd src
            export HOME="$TMPDIR/home" LANG=C.UTF-8 TZ=UTC
            mkdir -p "$HOME"
            ${script}
            touch $out
          '';
    in
    {
      devShells = forAllSystems (pkgs: {
        default = pkgs.mkShell {
          packages = devTools pkgs;
        };
      });

      formatter = forAllSystems (pkgs: pkgs.nixfmt);

      checks = forAllSystems (
        pkgs:
        lib.mapAttrs (mkCheck pkgs) {
          shac = ''
            shac check --all
          '';
          shac-tests = ''
            shac test
          '';
          python-tests = ''
            pytest
            pytest
          '';
        }
      );
    };
}
