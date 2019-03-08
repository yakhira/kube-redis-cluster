#!/bin/bash
set -e

SERVICE_NAME='redis-cluster'
POD_NAME=$(cat /etc/podinfo/pod_name)
POD_NAMESPACE=$(cat /etc/podinfo/pod_namespace)
PET_ORDINAL=$(echo $POD_NAME | rev | cut -d- -f1)
DNS_SUFFIX=$SERVICE_NAME.$POD_NAMESPACE.svc.cluster.local

redis-server /etc/redis.conf &

sleep 1

resolve_ip(){
  hostname=$1
  echo $(nslookup $hostname | awk -v name="${hostname}" '$0 ~ name {getline;print}' | cut -d " " -f2 | head -n 1)
}

get_master_num(){
  pod_num=$1
  master_num=0

  master_num=$[ $pod_num - 3 ]

  while [ $master_num -gt 2 ]
  do
    master_num=$[ $master_num - 3 ]
  done

  echo $master_num
}

forget_failed_nodes(){
  for failed_node in $(redis-cli cluster nodes | grep fail | awk '{print $1}')
  do
    echo "Forget failed node $failed_node"
    redis-cli cluster forget $failed_node
  done
}

echo "Pod name: "$POD_NAME

REDIS_SERVICE_IP=$(resolve_ip $SERVICE_NAME)
echo "Redis service ip: "$REDIS_SERVICE_IP

case "$PET_ORDINAL" in
  0)  redis-cli cluster addslots $(seq 0 5500)
      redis-cli cluster meet $(resolve_ip "$SERVICE_NAME-2.$DNS_SUFFIX") 6379
      redis-cli cluster meet $REDIS_SERVICE_IP 6379;;
  1)  redis-cli cluster addslots $(seq 5501 11000)
      redis-cli cluster meet $(resolve_ip "$SERVICE_NAME-0.$DNS_SUFFIX") 6379
      redis-cli cluster meet $REDIS_SERVICE_IP 6379;;
  2)  redis-cli cluster addslots $(seq 11000 16383)
      redis-cli cluster meet $(resolve_ip "$SERVICE_NAME-1.$DNS_SUFFIX") 6379
      redis-cli cluster meet $REDIS_SERVICE_IP 6379;;
  *)  # Other members of the cluster join as slaves
      # TODO: Get list of peers using the peer finder using an init container

      redis-cli cluster meet $REDIS_SERVICE_IP 6379

      forget_failed_nodes

      MASTER_NUM=$(get_master_num $PET_ORDINAL)

      echo "Resolving $SERVICE_NAME-$MASTER_NUM.$DNS_SUFFIX"
      MASTER_IP=$(resolve_ip "$SERVICE_NAME-$MASTER_NUM.$DNS_SUFFIX")

      echo "Extracting master id for $MASTER_IP"

      while : ; do
        MASTER_ID=$(redis-cli cluster nodes | grep $MASTER_IP | awk '{print $1}')

        [[ "$MASTER_ID" == "" ]] || break
      done

      echo "Replicate to $MASTER_ID"
      redis-cli cluster replicate $MASTER_ID;;
  esac     
wait