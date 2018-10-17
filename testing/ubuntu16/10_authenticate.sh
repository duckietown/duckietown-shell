#!/bin/bash
set -o nounset
set -ex
echo TOKEN=${TOKEN}

dts tok set ${TOKEN}
dts challenges info
dts challenges list
