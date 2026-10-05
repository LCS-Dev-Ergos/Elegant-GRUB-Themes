#! /usr/bin/env bash

# ----- FONT GENERATION ------------------------------------------------------ #

grub2-mkfont -o unifont-16.pf2 -s 16 unifont.otf
grub2-mkfont -o unifont-24.pf2 -s 24 unifont.otf
grub2-mkfont -o unifont-32.pf2 -s 32 unifont.otf
