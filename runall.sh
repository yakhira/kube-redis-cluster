#!/bin/sh

if [ "$1" != "" ];
then
    for i in  $(kubectl get pods | grep redis | awk '{print $1}')
    do 
        echo Pod: $i
        kubectl exec $i -- $1
        echo   
    done
fi