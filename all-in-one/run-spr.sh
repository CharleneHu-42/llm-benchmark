#!/bin/bash
source bigdl-nano-init -c
#source bigdl-llm-init
export OMP_NUM_THREADS=48
export TRANSFORMERS_OFFLINE=1

# set following parameters according to the actual specs of the test machine
numactl -C 0-47 -m 0 python $(dirname "$0")/run.py
