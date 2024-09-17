#!/bin/zsh

# The option --allow-missing-config is needed only if do not want an error when
# your .pre-commit-config.yaml is missing. If that file is missing and you have
# installed pre-commit hooks, then you will not be able to commit or push in gitkraken.
# Switching to branch create-apps will switch to the original gitinspector version
# 0.5dev, which has no pre-commit config file.

pre-commit install -t pre-commit --allow-missing-config
pre-commit install -t pre-push --allow-missing-config
