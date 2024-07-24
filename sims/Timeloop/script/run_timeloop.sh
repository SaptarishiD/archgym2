#!/usr/bin/sh
HOME="/home/workspace"

cd /home/workspace/src/timeloop-examples/workspace/final-project/example_designs/eyeriss_like

OUTPUT_DIR="./archgym2/sims/Timeloop/output"
LAYER_SHAPE="AlexNet/AlexNet_layer3.yaml"

# Invoke timeloop
echo " " | timeloop-mapper ./archgym2/sims/Timeloop/arch/eyeriss_like.yaml \
./archgym2/sims/Timeloop/arch/components/*.yaml \
./archgym2/sims/Timeloop/mapper/mapper.yaml constraints/*.yaml \
../../layer_shapes/$LAYER_SHAPE >$OUTPUT_DIR/timeloop_simulation_output.txt

mv timeloop-mapper.stats.txt ./archgym2/sims/Timeloop/output
