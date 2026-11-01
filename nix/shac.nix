# shac (Scalable Hermetic Analysis and Checks), built from a pinned source.
# Not in nixpkgs. The source vendors its Go dependencies (vendorHash = null).
{
  lib,
  stdenv,
  buildGoModule,
  patchelf,
  makeWrapper,
  src,
}:
let
  nsjail = if stdenv.hostPlatform.isAarch64 then "nsjail-linux-arm64" else "nsjail-linux-amd64";
in
buildGoModule {
  pname = "shac";
  version = "0-unstable-2026-10-02";
  inherit src;
  vendorHash = null;

  # Fall back to shac's unsandboxed runner when AppArmor blocks unprivileged user
  # namespaces (Ubuntu 24.04 default, incl. GitHub's ubuntu-latest); nsjail can't
  # start there. Candidate for upstreaming via github.com/dannyzen-innodata/shac.
  patches = [ ./patches/shac-apparmor-userns-fallback.patch ];
  subPackages = [ "." ];
  nativeBuildInputs = [
    patchelf
    makeWrapper
  ];

  # shac embeds a prebuilt, dynamically linked nsjail for its Linux sandbox. Point it
  # at Nix's loader and libraries so it runs on hosts (and Nix builds) without /lib64.
  postPatch = lib.optionalString stdenv.hostPlatform.isLinux ''
    patchelf \
      --set-interpreter "$(cat ${stdenv.cc}/nix-support/dynamic-linker)" \
      --set-rpath ${
        lib.makeLibraryPath [
          stdenv.cc.cc.lib
          stdenv.cc.libc
        ]
      } \
      internal/sandbox/${nsjail}
  '';

  # shac.textproto passes $NIX_STORE through as a read-only mount, so Nix-built tools
  # (whose dependencies live all over /nix/store) work inside shac's sandbox.
  postInstall = ''
    wrapProgram $out/bin/shac --set-default NIX_STORE /nix/store
  '';

  # Upstream's own test suite needs git fixtures and network; makor tests how it uses
  # shac instead (checks/tests/).
  doCheck = false;

  meta = {
    description = "Scalable Hermetic Analysis and Checks: Starlark-defined checks";
    homepage = "https://github.com/shac-project/shac";
    license = lib.licenses.asl20;
    mainProgram = "shac";
  };
}
