#!/usr/bin/env bash

# This script run the benchmark for the repositories taken from stdin
# You should provide:
# - temporary directory (where the repositories will be unpacked)
# - backend mapping file containing: the backend name, the backend api
#   URL and the sqlite db file.
# - the algorithms to be executed
#
# USAGE EXAMPLE:
# find /repositories/dir -name '*.tar.zst' | ./run_benchmark.sh /temporary/dir kb_state.txt stopngo file_priority


temp_dir=$1
kb_state=$2
log_file=$3

if [ ! -d "$temp_dir" ]; then
    echo "You should provide a valid temporary directory path"
    exit 1
fi

if [ "$kb_state" == '' ]; then
    echo "You should provide the file with mapped knowledge bases"
    exit 1
fi

if [ "$log_file" == '' ]; then
    echo "You should provide the file where the logs will be saved"
    exit 1
else
    log_file="-l ${log_file}"
fi

for i in "${@:4}"; do
    algos="$algos -a $i"
done

# print headers
echo "repo_id,origin,commit_id,kb_state,repo_size,algorithm_name,kb_queries,swhids_queried,scan_time"

while IFS= read -r repo;
do
    ./benchmark.py $repo $temp_dir $kb_state $algos $log_file
done
