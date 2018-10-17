#!/bin/bash
set -exu pipefail

echo DOCKER_USERNAME=${DOCKER_USERNAME}

dts challenges config --docker-username ${DOCKER_USERNAME}
