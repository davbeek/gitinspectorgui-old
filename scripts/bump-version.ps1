#!/usr/bin/env pwsh

$ROOT_DIR = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Definition)

$VERSION = Get-Content "$ROOT_DIR/src/gigui/version.txt" -Raw
python $ROOT_DIR/scripts/bump_version.py $VERSION
