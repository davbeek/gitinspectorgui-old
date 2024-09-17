#!/bin/zsh

SCRIPTDIR="${0:A:h}"

cd $SCRIPTDIR && {
    zsh app-create.zsh && zsh app-dmg.zsh
}
