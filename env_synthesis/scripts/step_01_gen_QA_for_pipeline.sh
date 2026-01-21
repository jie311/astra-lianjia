#!/bin/bash

export LOG_FILE_NAME="step_01_gen_QA_for_pipeline.log"
python src/step_01_gen_QA_for_pipeline.py \
    --mode [mode] \
    --model_name [model_name] \
    --output_dir [output_dir] \
    --num_workers [num_workers] \
    --batch_size [batch_size] \
    --min_hops [min_hops] \
    --max_hops [max_hops] \
    --num_repeats [num_repeats] \
    --domain [domain] \
    --lang [lang]
