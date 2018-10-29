#!/bin/bash
set -exu pipefail

echo TOKEN=${TOKEN}

dts tok set ${TOKEN}
dts challenges info
dts challenges list
