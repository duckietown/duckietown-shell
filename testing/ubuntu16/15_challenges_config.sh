#!/bin/bash
set -o nounset
set -ex

echo DOCKER_USERNAME=${DOCKER_USERNAME}

dts challenges config --docker-username ${DOCKER_USERNAME}
