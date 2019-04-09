#!/bin/sh

#PBS -q celltypes
#PBS -l walltime=24:00:00
#PBS -l nodes=16:ppn=16
#PBS -l mem=100g
#PBS -N Stage2
#PBS -r n
#PBS -m n

cd $PBS_O_WORKDIR

set -ex

source activate conda_env

# Relaunch batch job if not finished
qsub batch_job.sh –W depend=afternotok:$PBS_JOBID

OFFSPRING_SIZE=512
MAX_NGEN=20
seed=1


PWD=$(pwd)
export IPYTHONDIR=$PWD/.ipython
export IPYTHON_PROFILE=pbs.$PBS_JOBID

ipcontroller --init --ip='*' --sqlitedb --ping=30000 --profile=${IPYTHON_PROFILE} &
sleep 10
mpiexec -n 256 ipengine --timeout=3000 --profile=${IPYTHON_PROFILE} &
sleep 10

CHECKPOINTS_DIR="checkpoints"
mkdir -p ${CHECKPOINTS_DIR}

python Optim_Main.py             \
    -vv                                \
    --offspring_size=${OFFSPRING_SIZE} \
    --max_ngen=${MAX_NGEN}             \
    --seed=${seed}                     \
    --ipyparallel                      \
    --start                        \
    --checkpoint "${CHECKPOINTS_DIR}/seed${seed}.pkl" &

pid=$!
wait $pid

# If job finishes in time analyze result
mv ${CHECKPOINTS_DIR}/seed${seed}.pkl checkpoints_final/

# check if the job with 4th seed is finished
if [[ $seed = 4 ]]; then
    qsub analyze_results.sh
else
    seed_new=$(($seed+1))
    sed -i -e "s/seed=$seed/seed=$seed_new/g" batch_job.sh
    qsub batch_job.sh
fi
