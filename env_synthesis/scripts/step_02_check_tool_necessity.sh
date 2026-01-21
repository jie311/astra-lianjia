#!/bin/bash
export LOG_FILE_NAME="step_02_check_tool_necessity.log"
python src/step_02_check_tool_necessity.py \
    --input_file [inpath] \
    --model_name [modelname] \
    --output_file [outpath]
