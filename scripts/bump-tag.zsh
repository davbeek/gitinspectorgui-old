#!/bin/zsh

ROOT_DIR="${0:A:h:h}"

cd $ROOT_DIR && {
    version=$(<src/gigui/version.txt)
    python scripts/bump_tag.py $version
}
