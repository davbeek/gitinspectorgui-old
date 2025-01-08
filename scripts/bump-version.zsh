#!/bin/zsh

# Manually bump the version number in the src/gigui/version.txt file, then execute this
# script.

# To update the documentation version, manually update the version number in the
# gitinspectorgui-rtd repo in file docs/source/conf.py.

ROOT_DIR="${0:A:h:h}"
cd $ROOT_DIR && {
    version=$(<src/gigui/version.txt)
    python scripts/bump_version.py $version
}
