#!/bin/bash
numa_node=0
cores=$1

jemalloc_enable=t
current_date=$(date +%F)
if [[ $jemalloc_enable == "0" ]]; then
    source bigdl-llm-init -c
    log=../logs/transformers/output-$current_date.log
elif [[ $jemalloc_enable == "t" ]]; then
    source bigdl-llm-init -t
    log=../logs/transformers/tcmalloc-$cores-core-output-$current_date.log
else
    source bigdl-llm-init #-d
    log=../logs/transformers/jemalloc-output-$current_date.log
fi
export OMP_NUM_THREADS=$cores
export TRANSFORMERS_OFFLINE=1

echo "LD_PRELOAD=$LD_PRELOAD"
echo "MALLOC_CONF=$MALLOC_CONF"

# set following parameters according to the actual specs of the test machine
cd all-in-one/
numactl -C $[numa_node*cores]-$[numa_node*cores+cores-1] -m $numa_node python -u run.py 2>&1 | tee -a $log

