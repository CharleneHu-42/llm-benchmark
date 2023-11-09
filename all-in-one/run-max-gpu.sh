source /opt/intel/oneapi/setvars.sh
export LD_PRELOAD=${LD_PRELOAD}:${CONDA_PREFIX}/lib/libtcmalloc.so
export USE_XETLA=OFF
export SYCL_PI_LEVEL_ZERO_USE_IMMEDIATE_COMMANDLISTS=1
export ENABLE_SDP_FUSION=1

current_date=$(date +%F)
log=../logs/output-$current_date.log

numabind=$1
node=0
cores=`lscpu | grep "Core(s) per socket:" | awk '{print $NF}'`
if [[ $numabind == "1" ]]; then
        numacmd="numactl -C $[numa_node*cores]-$[numa_node*cores+cores-1] -m $node"
        log=../logs/numactl-output-$current_date.log
fi

export ZE_AFFINITY_MASK=0.0
$numacmd python -u run.py 2>&1 | tee -a $log # make sure config YAML file

