#!/bin/bash

#SBATCH -q premium 
#SBATCH -t 2:00:00
#SBATCH -N 8
#SBATCH -C haswell
#SBATCH -J 525133308_Passive
#SBATCH --mail-user=anin@alleninstitute.org
#SBATCH --mail-type=ALL


set -e
set -x

PWD=$(pwd)
LOGS=$PWD/logs
mkdir -p $LOGS

OFFSPRING_SIZE=512
MAX_NGEN=100

export IPYTHONDIR=${PWD}/.ipython
export IPYTHON_PROFILE=benchmark.${SLURM_JOBID}

ipcontroller --init --ip='*' --sqlitedb --profile=${IPYTHON_PROFILE} &
sleep 10
srun -n 256 -c 2 --cpu_bind=cores --output="${LOGS}/engine_%j_%2t.out" ipengine	--timeout=300 --profile=${IPYTHON_PROFILE} &
sleep 10

CHECKPOINTS_DIR="checkpoints"
mkdir -p ${CHECKPOINTS_DIR}

pids=""
for seed in 1; do
    python Optim_Main.py             \
        -vv                                \
        --compile                          \
        --offspring_size=${OFFSPRING_SIZE} \
        --max_ngen=${MAX_NGEN}             \
        --seed=${seed}                     \
        --ipyparallel                      \
        --start                        \
        --checkpoint "${CHECKPOINTS_DIR}/seed${seed}.pkl" &
    pids+="$! "
done

wait $pids

# Launch the passive+Ih optimization (Stage 1)
sh launch_stage1.sh