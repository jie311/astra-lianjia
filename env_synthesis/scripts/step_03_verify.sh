#!/bin/bash
export LOG_FILE_NAME="step_03_verify.log"
python src/step_03_verify.py \
    --input_file [inpath] \
    --model_name [modelname] \
    --output_file [outpath] \
    --max_concurrent [max_concurrent]
