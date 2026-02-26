{
  description = "TUI for accessing edziekanat of ZUT university";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
    }:

    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
      in
      {
        packages = {
          default = pkgs.python3Packages.buildPythonApplication {
            pname = "zutui";
            version = "1.0.0";
            src = ./.;
            pyproject = true;

            build-system = with pkgs.python3Packages; [
              setuptools
              wheel
            ];

            dependencies = with pkgs.python3Packages; [
              keyring
              textual
              requests
              beautifulsoup4
              appdirs
            ];

            meta = with pkgs.lib; {
              description = "TUI for accessing edziekanat of ZUT university";
              homepage = "https://github.com/shv187/zutui";
              license = licenses.mit;
              mainProgram = "zutui";
            };
          };
        };

        devShells = {
          default = pkgs.mkShell {
            inputsFrom = [ self.packages.${system}.default ];
          };
        };
      }

    );

}
