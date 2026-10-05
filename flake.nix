{
  description = "Tokyo Night GRUB theme, derived from vinceliuice's Elegant-grub2-themes";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      supportedSystems = [ "x86_64-linux" "aarch64-linux" ];
      forAllSystems = nixpkgs.lib.genAttrs supportedSystems;

      resolutions = {
        "1080p" = "1920x1080";
        "1440p" = "2560x1440";
        "1600p" = "2560x1600";
        "4k" = "3840x2160";
      };

      defaults = {
        type = "window";
        side = "left";
        screen = "1080p";
        photo = "mountain";
        logo = "cachyos";
        grade = "soft";
      };

      # Builds the theme with tools/build.py; theme directory is $out/tokyonight.
      mkTheme = pkgs: opts:
        let
          o = defaults // opts;
          python = pkgs.python3.withPackages (ps: [ ps.pillow ]);
        in
        pkgs.runCommand "grub-tokyonight" { nativeBuildInputs = [ python ]; } ''
          mkdir -p "$out"
          python3 ${self}/tools/build.py "$out/tokyonight" \
            -s ${o.screen} -p ${o.type} -i ${o.side} -g ${o.grade} \
            -l ${pkgs.lib.escapeShellArg o.logo} \
            -f ${pkgs.lib.escapeShellArg "${o.photo}"}
        '';
    in
    {
      packages = forAllSystems (system:
        let pkgs = nixpkgs.legacyPackages.${system}; in
        { default = mkTheme pkgs { }; });

      # `nix flake check` builds the theme with default options
      checks = forAllSystems (system: { theme = self.packages.${system}.default; });

      devShells = forAllSystems (system:
        let pkgs = nixpkgs.legacyPackages.${system}; in
        { default = pkgs.mkShell { packages = [ (pkgs.python3.withPackages (ps: [ ps.pillow ])) ]; }; });

      nixosModules.default = { config, lib, pkgs, ... }:
        let
          cfg = config.boot.loader.tokyonight-grub-theme;
          theme = mkTheme pkgs { inherit (cfg) type side screen logo grade; photo = cfg.photo; };
          themeDir = "${theme}/tokyonight";
          resolution = resolutions.${cfg.screen};
        in
        {
          options.boot.loader.tokyonight-grub-theme = {
            enable = lib.mkEnableOption "the Tokyo Night GRUB theme";
            type = lib.mkOption {
              type = lib.types.enum [ "window" "float" "sharp" "blur" ];
              default = defaults.type;
              description = "Theme style.";
            };
            side = lib.mkOption {
              type = lib.types.enum [ "left" "right" ];
              default = defaults.side;
              description = "Photo side.";
            };
            screen = lib.mkOption {
              type = lib.types.enum (builtins.attrNames resolutions);
              default = defaults.screen;
              description = "Screen resolution (1600p = 2560x1600).";
            };
            photo = lib.mkOption {
              type = lib.types.either lib.types.str lib.types.path;
              default = defaults.photo;
              example = lib.literalExpression "./background.jpg";
              description = "Name of a photo in backgrounds/ or path to an image (jpg, png, webp).";
            };
            logo = lib.mkOption {
              type = lib.types.str;
              default = defaults.logo;
              description = "Name of a logo in assets/logos/ or \"none\".";
            };
            grade = lib.mkOption {
              type = lib.types.enum [ "none" "soft" "full" ];
              default = defaults.grade;
              description = "Color grading of the photo towards the palette.";
            };
          };

          config = lib.mkIf cfg.enable {
            boot.loader.grub = {
              theme = themeDir;
              splashImage = "${themeDir}/background.jpg";
              gfxmodeEfi = "${resolution},auto";
              gfxmodeBios = "${resolution},auto";
              extraConfig = ''
                insmod gfxterm
                insmod png
              '';
            };
          };
        };
    };
}
