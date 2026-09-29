#!/bin/bash
# usage: perf.sh repo label task...   -> data/<repo>.perf.<label>.log
r=$1; l=$2; shift 2
cd src/$r && /usr/bin/time -p ./gradlew "$@" --profile --console=plain > ../../data/$r.perf.$l.log 2>&1
echo "exit=$?" >> ../../data/$r.perf.$l.log
