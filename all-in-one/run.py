#
# Copyright 2016 The BigDL Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#


# this code is copied from llama2 example test, and added performance test
import torch
import time

import numpy as np
from datetime import date

import os
current_dir = os.path.dirname(os.path.realpath(__file__))
benchmark_util_path = os.path.join(current_dir, '..')
import sys
sys.path.append(benchmark_util_path)
from benchmark_util import BenchmarkWrapper
from bigdl.llm.utils.common.log4Error import invalidInputError

LLAMA_IDS = ['meta-llama/Llama-2-7b-chat-hf','meta-llama/Llama-2-13b-chat-hf',
             'meta-llama/Llama-2-70b-chat-hf','decapoda-research/llama-7b-hf',
             'decapoda-research/llama-65b-hf','lmsys/vicuna-7b-v1.5',
             'lmsys/vicuna-13b-v1.3','project-baize/merged-baize-30b']

results = []


def run_model(repo_id, test_api, in_out_pairs, local_model_hub=None, warm_up=1, num_trials=3, num_beams=1, low_bit='sym_int4'):
    # TODO: make a parameter
    result= {}
    if test_api == 'transformer_int4':
        result = run_transformer_int4(repo_id, local_model_hub, in_out_pairs, warm_up, num_trials, num_beams, low_bit)
    elif test_api == 'native_int4':
        run_native_int4(repo_id, local_model_hub, in_out_pairs, warm_up, num_trials)
    elif test_api == 'optimize_model':
        result = run_optimize_model(repo_id, local_model_hub, in_out_pairs, warm_up, num_trials, num_beams, low_bit)
    elif test_api == 'transformer_int4_gpu':
        result = run_transformer_int4_gpu(repo_id, local_model_hub, in_out_pairs, warm_up, num_trials, num_beams, low_bit)
    elif test_api == 'optimize_model_gpu':
        result = run_optimize_model_gpu(repo_id, local_model_hub, in_out_pairs, warm_up, num_trials, num_beams, low_bit)
    elif test_api == 'pytorch_autocast_bf16':
        result = run_pytorch_autocast_bf16(repo_id, local_model_hub, in_out_pairs, warm_up, num_trials, num_beams)
    elif test_api == 'ipex_fp16_gpu':
        result = run_ipex_fp16_gpu(repo_id, local_model_hub, in_out_pairs, warm_up, num_trials, num_beams)

    for in_out_pair in in_out_pairs:
        if result:
            results.append([repo_id,
                            round(np.mean(result[in_out_pair], axis=0)[0]*1000.0, 2),
                            round(np.mean(result[in_out_pair], axis=0)[1]*1000.0, 2),
                            round(np.mean(result[in_out_pair], axis=0)[2]*1000.0, 2),
                            round(np.mean(result[in_out_pair], axis=0)[3]*1000.0, 2),
                            in_out_pair,
                            f'{int(np.mean(result[in_out_pair], axis=0)[4])}' +
                            f'-{int(np.mean(result[in_out_pair], axis=0)[5])}',
                            num_beams,
                            low_bit])


def get_model_path(repo_id, local_model_hub):
    if local_model_hub:
        repo_model_name = repo_id.split("/")[1]
        local_model_path = local_model_hub + os.path.sep + repo_model_name
        invalidInputError(os.path.isdir(local_model_path),
                          local_model_path + " not exists!, Please check your models' folder.")
        return local_model_path
    else:
        return repo_id


def run_native_int4(repo_id,
                    local_model_hub,
                    in_out_pairs,
                    warm_up,
                    num_trials):
    model_path = get_model_path(repo_id, local_model_hub)
    from bigdl.llm.transformers import BigdlNativeForCausalLM
    from bigdl.llm import llm_convert
    if "chatglm" in repo_id.lower():
        family = "chatglm"
    elif "llama" in repo_id.lower():
        family = "llama"
    else:
        invalidInputError(False, "Model family unknown: " + repo_id)

    bigdl_llm_path = llm_convert(model=model_path,
                                 outfile="./", outtype='int4', model_family=family)
    for in_out in in_out_pairs:
        in_out_len = in_out.split("-")
        in_len = int(in_out_len[0])
        out_len = int(in_out_len[1])
        input_str = open(f"prompt/{in_len}.txt", 'r').read()
        # As different tokenizer has different encodings,
        # slice the input_ids to ensure the prompt length is required length.
        n_ctx = in_len + out_len if in_len + out_len > 512 else 512
        for i in range(num_trials + warm_up):
            model = BigdlNativeForCausalLM.from_pretrained(bigdl_llm_path, model_family=family, n_ctx=n_ctx)
            input_ids = model.tokenize(input_str)
            input_ids = input_ids[:in_len]
            true_input = model.batch_decode(input_ids)
            st = time.perf_counter()
            output = model(true_input, max_tokens=out_len)
            end = time.perf_counter()
            print("model generate cost: " + str(end - st))
            print(output)

    os.remove(bigdl_llm_path)


def run_transformer_int4(repo_id,
                         local_model_hub,
                         in_out_pairs,
                         warm_up,
                         num_trials,
                         num_beams,
                         low_bit):
    from bigdl.llm.transformers import AutoModel, AutoModelForCausalLM
    from transformers import AutoTokenizer, LlamaTokenizer

    model_path = get_model_path(repo_id, local_model_hub)
    # Load model in 4 bit,
    # which convert the relevant layers in the model into INT4 format
    st = time.perf_counter()
    if repo_id in ['THUDM/chatglm-6b', 'THUDM/chatglm2-6b']:
        model = AutoModel.from_pretrained(model_path, load_in_low_bit=low_bit, trust_remote_code=True, torch_dtype='auto')
        tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
    elif repo_id in LLAMA_IDS:
        model = AutoModelForCausalLM.from_pretrained(model_path, load_in_low_bit=low_bit, trust_remote_code=True,
                                                     use_cache=True)
        tokenizer = LlamaTokenizer.from_pretrained(model_path, trust_remote_code=True)
    else:
        model = AutoModelForCausalLM.from_pretrained(model_path, load_in_low_bit=low_bit, trust_remote_code=True,
                                                     use_cache=True)
        tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
    end = time.perf_counter()
    print(">> loading of model costs {}s".format(end - st))

    model = BenchmarkWrapper(model, do_print=True)

    result = {}
    with torch.inference_mode():
        for in_out in in_out_pairs:
            in_out_len = in_out.split("-")
            in_len = int(in_out_len[0])
            out_len = int(in_out_len[1])
            # As different tokenizer has different encodings,
            # in_len.txt maybe shorter than we need,
            # use much longer context to make sure input length
            test_length = min(in_len*2, 8192)
            while test_length not in [32, 256, 1024, 2048, 8192]:
                test_length = test_length * 2
            input_str = open(f"prompt/{test_length}.txt", 'r').read()
            # As different tokenizer has different encodings,
            # slice the input_ids to ensure the prompt length is required length.
            input_ids = tokenizer.encode(input_str, return_tensors="pt")
            input_ids = input_ids[:, :in_len]
            if not repo_id in LLAMA_IDS:
                true_str = tokenizer.batch_decode(input_ids)[0]
                input_ids = tokenizer.encode(true_str, return_tensors="pt")
            actual_in_len = input_ids.shape[1]
            result[in_out] = []
            for i in range(num_trials + warm_up):
                st = time.perf_counter()
                output_ids = model.generate(input_ids, do_sample=False, max_new_tokens=out_len,
                                            min_new_tokens=out_len,
                                            num_beams=num_beams)
                end = time.perf_counter()
                print("model generate cost: " + str(end - st))
                output = tokenizer.batch_decode(output_ids)
                print(output[0])
                actual_out_len = output_ids.shape[1] - actual_in_len
                if i >= warm_up:
                    result[in_out].append([model.first_cost, model.rest_cost_mean, model.rest_cost_p90, model.encoder_time,
                                           actual_in_len, actual_out_len])
    return result

def run_pytorch_autocast_bf16(repo_id,
                         local_model_hub,
                         in_out_pairs,
                         warm_up,
                         num_trials,
                         num_beams):
    from transformers import AutoTokenizer, AutoModel, AutoModelForCausalLM, LlamaTokenizer

    model_path = get_model_path(repo_id, local_model_hub)
    st = time.perf_counter()
    if repo_id in ['THUDM/chatglm-6b', 'THUDM/chatglm2-6b']:
        # TODO: need verify chatglm family run bf16.
        print("Currently pytorch do not support bfloat16 on cpu for chatglm models. Will skip it")
        return
    elif repo_id in LLAMA_IDS:
        model = AutoModelForCausalLM.from_pretrained(model_path, trust_remote_code=True, torch_dtype=torch.bfloat16,
                                                     use_cache=True)
        # Need to use LlamaTokenizer, reason please refer to issue: https://github.com/intel-analytics/BigDL/issues/8944
        tokenizer = LlamaTokenizer.from_pretrained(model_path, trust_remote_code=True)
    else:
        model = AutoModelForCausalLM.from_pretrained(model_path, trust_remote_code=True, torch_dtype=torch.bfloat16,
                                                     use_cache=True)
        tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
    end = time.perf_counter()
    print(">> loading of model costs {}s".format(end - st))

    model = BenchmarkWrapper(model)
    result = {}
    with torch.inference_mode(), torch.autocast("cpu"):
        for in_out in in_out_pairs:
            in_out_len = in_out.split("-")
            in_len = int(in_out_len[0])
            out_len = int(in_out_len[1])
            # As different tokenizer has different encodings,
            # in_len.txt maybe shorter than we need,
            # use much longer context to make sure input length
            test_length = min(in_len*2, 8192)
            while test_length not in [32, 256, 1024, 2048, 8192]:
                test_length = test_length * 2
            input_str = open(f"prompt/{test_length}.txt", 'r').read()
            # As different tokenizer has different encodings,
            # slice the input_ids to ensure the prompt length is required length.
            input_ids = tokenizer.encode(input_str, return_tensors="pt")
            input_ids = input_ids[:, :in_len]
            if not repo_id in LLAMA_IDS:
                true_str = tokenizer.batch_decode(input_ids)[0]
                input_ids = tokenizer.encode(true_str, return_tensors="pt")
            actual_in_len = input_ids.shape[1]
            result[in_out] = []
            print("input tokens: {}".format(input_ids.shape[1]))
            for i in range(num_trials + warm_up):
                st = time.perf_counter()
                output_ids = model.generate(input_ids, do_sample=False, max_new_tokens=out_len,
                                            min_new_tokens=out_len,
                                            num_beams=num_beams)
                end = time.perf_counter()
                print("model generate cost: " + str(end - st))
                output = tokenizer.batch_decode(output_ids)
                print(output[0])
                actual_out_len = output_ids.shape[1] - actual_in_len
                if i >= warm_up:
                    result[in_out].append([model.first_cost, model.rest_cost_mean, model.rest_cost_p90, model.encoder_time,
                                           actual_in_len, actual_out_len])
    return result

def run_optimize_model(repo_id,
                       local_model_hub,
                       in_out_pairs,
                       warm_up,
                       num_trials,
                       num_beams,
                       low_bit):
    from transformers import AutoModel, AutoModelForCausalLM, AutoTokenizer, LlamaTokenizer
    from bigdl.llm import optimize_model

    model_path = get_model_path(repo_id, local_model_hub)
    # Load model in 4 bit,
    # which convert the relevant layers in the model into INT4 format
    st = time.perf_counter()
    if repo_id in ['THUDM/chatglm-6b', 'THUDM/chatglm2-6b']:
        model = AutoModel.from_pretrained(model_path, torch_dtype='auto', low_cpu_mem_usage=True, trust_remote_code=True)
        model = optimize_model(model, low_bit=low_bit)
        tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
    elif repo_id in LLAMA_IDS:
        model = AutoModelForCausalLM.from_pretrained(model_path, trust_remote_code=True,
                                                     use_cache=True, low_cpu_mem_usage=True)
        model = optimize_model(model, low_bit=low_bit)
        tokenizer = LlamaTokenizer.from_pretrained(model_path, trust_remote_code=True)
    else:
        model = AutoModelForCausalLM.from_pretrained(model_path, torch_dtype='auto', low_cpu_mem_usage=True)
        model = optimize_model(model, low_bit=low_bit)
        tokenizer = AutoTokenizer.from_pretrained(model_path)
    end = time.perf_counter()
    print(">> loading of model costs {}s".format(end - st))

    model = BenchmarkWrapper(model, do_print=True)

    result = {}
    with torch.inference_mode():
        for in_out in in_out_pairs:
            in_out_len = in_out.split("-")
            in_len = int(in_out_len[0])
            out_len = int(in_out_len[1])
            # As different tokenizer has different encodings,
            # in_len.txt maybe shorter than we need,
            # use much longer context to make sure input length
            test_length = min(in_len*2, 8192)
            while test_length not in [32, 256, 1024, 2048, 8192]:
                test_length = test_length * 2
            input_str = open(f"prompt/{test_length}.txt", 'r').read()
            # As different tokenizer has different encodings,
            # slice the input_ids to ensure the prompt length is required length.
            input_ids = tokenizer.encode(input_str, return_tensors="pt")
            input_ids = input_ids[:, :in_len]
            true_str = tokenizer.batch_decode(input_ids)[0]
            input_ids = tokenizer.encode(true_str, return_tensors="pt")
            actual_in_len = input_ids.shape[1]
            result[in_out] = []
            for i in range(num_trials + warm_up):
                st = time.perf_counter()
                output_ids = model.generate(input_ids, do_sample=False, max_new_tokens=out_len,
                                            num_beams=num_beams)
                end = time.perf_counter()
                print("model generate cost: " + str(end - st))
                output = tokenizer.batch_decode(output_ids)
                print(output[0])
                actual_out_len = output_ids.shape[1] - actual_in_len
                if i >= warm_up:
                    result[in_out].append([model.first_cost, model.rest_cost_mean, model.encoder_time,
                                           actual_in_len, actual_out_len])
    return result


def run_transformer_int4_gpu(repo_id,
                             local_model_hub,
                             in_out_pairs,
                             warm_up,
                             num_trials,
                             num_beams,
                             low_bit):
    from bigdl.llm.transformers import AutoModel, AutoModelForCausalLM
    from transformers import AutoTokenizer, GPTJForCausalLM, LlamaTokenizer
    import intel_extension_for_pytorch as ipex
    model_path = get_model_path(repo_id, local_model_hub)
    # Load model in 4 bit,
    # which convert the relevant layers in the model into INT4 format
    st = time.perf_counter()
    if repo_id in ['THUDM/chatglm-6b', 'THUDM/chatglm2-6b']:
        model = AutoModel.from_pretrained(model_path, load_in_low_bit=low_bit, optimize_model=True,
                                          trust_remote_code=True, use_cache=True)
        tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        model = model.to('xpu')
    elif repo_id in LLAMA_IDS:
        model = AutoModelForCausalLM.from_pretrained(model_path, load_in_low_bit=low_bit, trust_remote_code=True,
                                                     use_cache=True)
        tokenizer = LlamaTokenizer.from_pretrained(model_path, trust_remote_code=True)
        model = model.to('xpu')
    else:
        model = AutoModelForCausalLM.from_pretrained(model_path, optimize_model=True, load_in_low_bit=low_bit,
                                                     trust_remote_code=True, use_cache=True)
        tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        model = model.to('xpu')
        if isinstance(model, GPTJForCausalLM):
            # For gpt-j model family, this optimization can provide a better performance.
            model = ipex.optimize(model.eval(), inplace=True)
    end = time.perf_counter()
    print(">> loading of model costs {}s".format(end - st))

    model = BenchmarkWrapper(model)

    result = {}
    with torch.inference_mode():
        for in_out in in_out_pairs:
            in_out_len = in_out.split("-")
            in_len = int(in_out_len[0])
            out_len = int(in_out_len[1])
            # As different tokenizer has different encodings,
            # in_len.txt maybe shorter than we need,
            # use much longer context to make sure input length
            test_length = min(in_len*2, 8192)
            while test_length not in [32, 256, 1024, 2048, 8192]:
                test_length = test_length * 2
            input_str = open(f"prompt/{test_length}.txt", 'r').read()
            # As different tokenizer has different encodings,
            # slice the input_ids to ensure the prompt length is required length.
            input_ids = tokenizer.encode(input_str, return_tensors="pt")
            input_ids = input_ids[:, :in_len]
            true_str = tokenizer.batch_decode(input_ids)[0]
            input_ids = tokenizer.encode(true_str, return_tensors="pt").to('xpu')
            actual_in_len = input_ids.shape[1]
            result[in_out] = []
            for i in range(num_trials + warm_up):
                st = time.perf_counter()
                output_ids = model.generate(input_ids, do_sample=False, max_new_tokens=out_len,
                                            num_beams=num_beams)
                torch.xpu.synchronize()
                end = time.perf_counter()
                output_ids = output_ids.cpu()
                print("model generate cost: " + str(end - st))
                output = tokenizer.batch_decode(output_ids)
                print(output[0])
                actual_out_len = output_ids.shape[1] - actual_in_len
                if i >= warm_up:
                    result[in_out].append([model.first_cost, model.rest_cost_mean, model.encoder_time,
                                           actual_in_len, actual_out_len])
    torch.xpu.empty_cache()
    return result


def run_optimize_model_gpu(repo_id,
                           local_model_hub,
                           in_out_pairs,
                           warm_up,
                           num_trials,
                           num_beams,
                           low_bit):
    from transformers import AutoModel, AutoModelForCausalLM, AutoTokenizer, GPTJForCausalLM, LlamaTokenizer
    from bigdl.llm import optimize_model
    import intel_extension_for_pytorch as ipex
    model_path = get_model_path(repo_id, local_model_hub)
    # Load model in 4 bit,
    # which convert the relevant layers in the model into INT4 format
    st = time.perf_counter()
    if repo_id in ['THUDM/chatglm-6b', 'THUDM/chatglm2-6b']:
        model = AutoModel.from_pretrained(model_path, torch_dtype='auto', low_cpu_mem_usage=True,
                                          trust_remote_code=True, use_cache=True)
        model = optimize_model(model, low_bit=low_bit)
        tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        model = model.to('xpu')
    elif repo_id in LLAMA_IDS:
        model = AutoModelForCausalLM.from_pretrained(model_path, load_in_4bit=True, trust_remote_code=True,
                                                     use_cache=True, low_cpu_mem_usage=True)
        model = optimize_model(model, low_bit=low_bit)
        tokenizer = LlamaTokenizer.from_pretrained(model_path, trust_remote_code=True)
        model = model.to('xpu')
    else:
        model = AutoModelForCausalLM.from_pretrained(model_path, torch_dtype='auto', low_cpu_mem_usage=True,
                                                     trust_remote_code=True, use_cache=True)
        model = optimize_model(model, low_bit=low_bit)
        tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        model = model.to('xpu')
        if isinstance(model, GPTJForCausalLM):
            # For gpt-j model family, this optimization can provide a better performance.
            model = ipex.optimize(model.eval(), inplace=True)
    end = time.perf_counter()
    print(">> loading of model costs {}s".format(end - st))

    model = BenchmarkWrapper(model)

    result = {}
    with torch.inference_mode():
        for in_out in in_out_pairs:
            in_out_len = in_out.split("-")
            in_len = int(in_out_len[0])
            out_len = int(in_out_len[1])
            # As different tokenizer has different encodings,
            # in_len.txt maybe shorter than we need,
            # use much longer context to make sure input length
            test_length = min(in_len*2, 8192)
            while test_length not in [32, 256, 1024, 2048, 8192]:
                test_length = test_length * 2
            input_str = open(f"prompt/{test_length}.txt", 'r').read()
            # As different tokenizer has different encodings,
            # slice the input_ids to ensure the prompt length is required length.
            input_ids = tokenizer.encode(input_str, return_tensors="pt")
            input_ids = input_ids[:, :in_len]
            true_str = tokenizer.batch_decode(input_ids)[0]
            input_ids = tokenizer.encode(true_str, return_tensors="pt").to('xpu')
            actual_in_len = input_ids.shape[1]
            result[in_out] = []
            for i in range(num_trials + warm_up):
                st = time.perf_counter()
                output_ids = model.generate(input_ids, do_sample=False, max_new_tokens=out_len,
                                            num_beams=num_beams)
                torch.xpu.synchronize()
                end = time.perf_counter()
                output_ids = output_ids.cpu()
                print("model generate cost: " + str(end - st))
                output = tokenizer.batch_decode(output_ids)
                actual_out_len = output_ids.shape[1] - actual_in_len
                print(output[0])
                if i >= warm_up:
                    result[in_out].append([model.first_cost, model.rest_cost_mean, model.encoder_time,
                                           actual_in_len, actual_out_len])
    torch.xpu.empty_cache()
    return result


def run_ipex_fp16_gpu(repo_id,
                      local_model_hub,
                      in_out_pairs,
                      warm_up,
                      num_trials,
                      num_beams):
    from transformers import AutoModel, AutoModelForCausalLM
    from transformers import AutoTokenizer, GPTJForCausalLM, LlamaTokenizer
    import intel_extension_for_pytorch as ipex
    model_path = get_model_path(repo_id, local_model_hub)
    st = time.perf_counter()
    if repo_id in ['THUDM/chatglm-6b', 'THUDM/chatglm2-6b']:
        model = AutoModel.from_pretrained(model_path, trust_remote_code=True, use_cache=True)
        tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        model = model.half().to('xpu')
    elif repo_id in LLAMA_IDS:
        model = AutoModelForCausalLM.from_pretrained(model_path, trust_remote_code=True,
                                                     use_cache=True)
        tokenizer = LlamaTokenizer.from_pretrained(model_path, trust_remote_code=True)
        model = model.half().to('xpu')
    else:
        model = AutoModelForCausalLM.from_pretrained(model_path, trust_remote_code=True, use_cache=True)
        tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        model = model.half().to('xpu')
        if isinstance(model, GPTJForCausalLM):
            # For gpt-j model family, this optimization can provide a better performance.
            model = ipex.optimize(model.eval(), inplace=True)
    end = time.perf_counter()
    print(">> loading of model costs {}s".format(end - st))

    model = BenchmarkWrapper(model)

    result = {}
    with torch.inference_mode():
        for in_out in in_out_pairs:
            in_out_len = in_out.split("-")
            in_len = int(in_out_len[0])
            out_len = int(in_out_len[1])
            # As different tokenizer has different encodings,
            # in_len.txt maybe shorter than we need,
            # use much longer context to make sure input length
            test_length = min(in_len*2, 8192)
            while test_length not in [32, 256, 1024, 2048, 8192]:
                test_length = test_length * 2
            input_str = open(f"prompt/{test_length}.txt", 'r').read()
            # As different tokenizer has different encodings,
            # slice the input_ids to ensure the prompt length is required length.
            input_ids = tokenizer.encode(input_str, return_tensors="pt")
            input_ids = input_ids[:, :in_len]
            true_str = tokenizer.batch_decode(input_ids)[0]
            input_ids = tokenizer.encode(true_str, return_tensors="pt").to('xpu')
            actual_in_len = input_ids.shape[1]
            result[in_out] = []
            for i in range(num_trials + warm_up):
                st = time.perf_counter()
                output_ids = model.generate(input_ids, do_sample=False, max_new_tokens=out_len,
                                            num_beams=num_beams)
                torch.xpu.synchronize()
                end = time.perf_counter()
                output_ids = output_ids.cpu()
                print("model generate cost: " + str(end - st))
                output = tokenizer.batch_decode(output_ids)
                actual_out_len = output_ids.shape[1] - actual_in_len
                print(output[0])
                if i >= warm_up:
                    result[in_out].append([model.first_cost, model.rest_cost_mean, model.encoder_time,
                                           actual_in_len, actual_out_len])
    torch.xpu.empty_cache()
    return result


if __name__ == '__main__':
    from omegaconf import OmegaConf
    conf = OmegaConf.load(f'{current_dir}/config.yaml')
    today = date.today()
    
    import pandas as pd
    import traceback
    import subprocess
    for api in conf.test_api:
        print("Tesing API", conf.test_api)
        for model in conf.repo_id:
#            subprocess.run(['bash', '/root/yabai/scripts/clean-cache.sh'], check=True, text=True)
            try:
                run_model(model, api, conf['in_out_pairs'], conf['local_model_hub'], conf['warm_up'], conf['num_trials'], conf['num_beams'], conf['low_bit'])
                df = pd.DataFrame(results, columns=['model', '1st token avg latency (ms)', '2+ avg latency (ms/token)', '2+ p90 latency (ms/token)','encoder time (ms)',
                                                'input/output tokens', 'actual input/output tokens', 'num_beams', 'low_bit'])
    
                df.to_csv(f'{current_dir}/{api}-results-{today}.csv', mode='a')
            except Exception as e:
                traceback.print_exc()

        results = []
