#!/bin/sh

for i in A B C D E F G H K L
do
    echo docker exec redis redis-cli -h 192.168.100.1 -p 30288 SET $i$i$i 0
done

for i in A B C D E F G H K L
do
    docker exec redis redis-cli -h 192.168.100.1 -p 30288 GET $i$i$i
done