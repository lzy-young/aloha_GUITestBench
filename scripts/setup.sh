#!/bin/bash
AVDNAME=$1
PORT=$2
GRPC_PORT=$3
export EMULATOR=/your/local/path/to/emulator
${EMULATOR} -avd ${AVDNAME} -no-snapshot -port ${PORT} -grpc ${GRPC_PORT}