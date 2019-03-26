#!/bin/sh

#SBATCH -p prod
#SBATCH -n 256
#SBATCH -t 4:00:00
#SBATCH -C cpu|nvme
#SBATCH -A proj36
#SBATCH --mail-type=ALL
#SBATCH -J Stage0
#SBATCH --signal=B:USR1@60

run_dependent_script() {
func="$1" ; shift
for sig ; do
trap "$func $sig" "$sig"
done
}

# trap function to launch the passive+Ih optimization (Stage 1)
func_trap() {
sbatch chain_job.sh
}

#submit launch script upon signal USR1
run_dependent_script func_trap USR1

set -ex

source activate ateam_opt

PWD=$(pwd)
LOGS=$PWD/logs
mkdir -p $LOGS

OFFSPRING_SIZE=512
MAX_NGEN=50
seed=1

export IPYTHONDIR=${PWD}/.ipython
export IPYTHON_PROFILE=benchmark.${SLURM_JOBID}

ipcontroller --init --ip='*' --sqlitedb --ping=30000 --profile=${IPYTHON_PROFILE} &
sleep 10
srun -n 256 --output="${LOGS}/engine_%j_%2t.out" ipengine --timeout=3000 --profile=${IPYTHON_PROFILE} &
sleep 10

CHECKPOINTS_DIR="checkpoints"
mkdir -p ${CHECKPOINTS_DIR}

python Optim_Main.py             \
    -vv                                \
    --compile                          \
    --offspring_size=${OFFSPRING_SIZE} \
    --max_ngen=${MAX_NGEN}             \
    --seed=${seed}                     \
    --ipyparallel                      \
    --start                         \
    --checkpoint "${CHECKPOINTS_DIR}/seed${seed}.pkl" &

pid=$!
wait $pid

# Launch the passive+Ih optimization (Stage 1)
sbatch chain_job.sh
