{
  description = "Flake to manage elegant grub2 themes from vinceliuice";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    elegant-grub2-theme-src = {
      url = "github:vinceliuice/Elegant-grub2-themes";
      flake = false;
    };
  };

  outputs = { self, nixpkgs, elegant-grub2-theme-src }:
    let
      supportedSystems = [ "x86_64-linux" "aarch64-linux" ];
      forAllSystems = nixpkgs.lib.genAttrs supportedSystems;
    in
    {
      packages = forAllSystems (system: 
        let 
          pkgs = nixpkgs.legacyPackages.${system};
        in {
          default = pkgs.stdenv.mkDerivation {
            name = "elegant-grub2-theme-source";
            src = elegant-grub2-theme-src;
            
            installPhase = ''
              mkdir -p $out
              cp -r ./* $out/
            '';
          };
        }
      );

      nixosModules.default = { config, lib, pkgs, ... }:
        let
          cfg = config.boot.loader.elegant-grub2-theme;
          
          resolutions = {
            "1080p" = "1920x1080";
            "2k" = "2560x1440";
            "4k" = "3840x2160";
          };
          
          themeName = "Elegant-${cfg.theme}-${cfg.type}-${cfg.side}-${cfg.color}";
          
          elegant-grub2-theme = pkgs.stdenv.mkDerivation {
            name = "elegant-grub2-theme";
            src = elegant-grub2-theme-src;
            buildInputs = [ pkgs.imagemagick ];
            installPhase = ''
              mkdir -p $out/grub/themes
              
              # Generate theme
              bash ./generate.sh \
                -d "$out/grub/themes" \
                -t ${cfg.theme} \
                -p ${cfg.type} \
                -i ${cfg.side} \
                -c ${cfg.color} \
                -s ${cfg.screen} \
                -l ${cfg.logo}
              
              ${lib.optionalString (cfg.splashImage != null) ''
                # Find the generated theme directory and replace background
                theme_dir=$(find $out/grub/themes -maxdepth 1 -type d -name "Elegant-*" | head -n 1)
                if [ -n "$theme_dir" ] && [ -f "$theme_dir/background.jpg" ]; then
                  rm -f "$theme_dir/background.jpg"
                  ${pkgs.imagemagick}/bin/convert ${cfg.splashImage} "$theme_dir/background.jpg"
                fi
              ''}
            '';
          };
          
          resolution = resolutions."${cfg.screen}";
        in
        {
          options.boot.loader.elegant-grub2-theme = {
            enable = lib.mkOption {
              default = false;
              example = true;
              type = lib.types.bool;
              description = ''
                Enable elegant grub2 theming
              '';
            };
            theme = lib.mkOption {
              default = "forest";
              example = "forest";
              type = lib.types.enum [ "forest" "mojave" "mountain" "wave" ];
              description = ''
                Background theme variant to use for grub2.
              '';
            };
            type = lib.mkOption {
              default = "window";
              example = "window";
              type = lib.types.enum [ "window" "float" "sharp" "blur" ];
              description = ''
                Theme style variant to use for grub2.
              '';
            };
            side = lib.mkOption {
              default = "left";
              example = "left";
              type = lib.types.enum [ "left" "right" ];
              description = ''
                Picture display side for grub2.
              '';
            };
            color = lib.mkOption {
              default = "dark";
              example = "dark";
              type = lib.types.enum [ "dark" "light" ];
              description = ''
                Background color variant to use for grub2.
              '';
            };
            screen = lib.mkOption {
              default = "1080p";
              example = "1080p";
              type = lib.types.enum [ "1080p" "2k" "4k" ];
              description = ''
                The screen display variant to use for grub2.
              '';
            };
            logo = lib.mkOption {
              default = "default";
              example = "default";
              type = lib.types.enum [ "default" "system" ];
              description = ''
                Logo variant to use for grub2.
              '';
            };
            splashImage = lib.mkOption {
              default = null;
              example = "/my/path/background.jpg";
              type = lib.types.nullOr lib.types.path;
              description = ''
                The path of the image to use for background (must be jpg or png).
              '';
            };
          };

          config = lib.mkIf cfg.enable {
            boot.loader.grub = {
              theme = "${elegant-grub2-theme}/grub/themes/${themeName}";
              splashImage = "${elegant-grub2-theme}/grub/themes/${themeName}/background.jpg";
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
