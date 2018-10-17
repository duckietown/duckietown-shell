#!/bin/bash
set -exu pipefail

git clone -b v3 https://github.com/duckietown/challenge-aido1_luck-template-python.git

cd challenge-aido1_luck-template-python

dts challenges evaluate
dts challenges submit
