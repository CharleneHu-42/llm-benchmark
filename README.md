# llm-benchmark
BigDL LLM benchmark kit

## Setup Environment
    conda create -n llm-benchmark python=3.9
	pip install -r requirements.txt
Install `libunwind-devel`, `libunwind` and `numactl` in OS

## Run Benchmark On CPU
Edit `all-in-one/config.yaml` according to test requirements

    cd all-in-one
	source bigdl-llm-init -t
	export OMP_NUM_THREADS=$cores
	numactl -C $[numa_node*cores]-$[numa_node*cores_per_node+cores-1] -m $numa_node python run.py

Note that `<cores>` and `<numa_node>` corresponds to core number and numa node we want to run on. 
