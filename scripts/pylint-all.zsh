#!/bin/zsh

# ROOT_DIR is the root dir of the repo = the parent dir of the directory of this script
ROOTDIR="${0:A:h:h}"

cd $ROOTDIR/src/gigui && {
    pylint --rcfile ../../.pylintrc $(find . -name "*.py" ! -name xx.py ! -name __main__.py | sort)
}
