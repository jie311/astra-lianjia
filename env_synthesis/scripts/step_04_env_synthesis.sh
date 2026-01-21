#!/bin/bash
export LOG_FILE_NAME="step_04_env_synthesis.log"
python src/step_04_env_synthesis.py \
    --input_file [inpath] \
    --model_name [modelname] \
    --output_file [outpath] \
    --threshold [threshold] # threshold should according to the verify result distribution,normally the threshold is the value of 85% quantile
