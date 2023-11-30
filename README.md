# QWen model inference Benchmark with BigDL LLM 

## Setup Environment
    conda create -n llm-benchmark python=3.9
	pip install -r requirements.txt
Install `libunwind-devel`, `libunwind` and `numactl` in OS:
	yum install libunwind-devel libunwind numactl 

## Download Model
	curl -s https://packagecloud.io/install/repositories/github/git-lfs/script.rpm.sh | sudo bash
	yum install git-lfs
	git lfs install
	git clone https://huggingface.co/Qwen/Qwen-7B-Chat

## Run Benchmark On CPU
Edit `local_model_hub` in `all-in-one/config.yaml` according to the model path

    cd all-in-one
	source bigdl-llm-init -t
	export OMP_NUM_THREADS=32
	numactl -C 0-31 -m 0 python run.py
