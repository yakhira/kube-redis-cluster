docker build --force-rm --no-cache --squash -t redis-cluster .
kubectl delete -f deployments/redis.yaml
docker rmi 192.168.100.1:5000/redis-cluster
docker tag redis-cluster 192.168.100.1:5000/redis-cluster
docker push 192.168.100.1:5000/redis-cluster
kubectl create -f deployments/redis.yaml
docker rmi redis-cluster
docker rmi $(docker images | grep none | awk '{print $3}')
