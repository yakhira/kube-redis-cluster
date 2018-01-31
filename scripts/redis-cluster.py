import requests
import os
import redis
import sys
import argparse
import time
import xmlrpc.client
import signal

__author__ = "Ruslan Iakhin"

requests.urllib3.disable_warnings()

KUBERNETES_SERVICE_HOST = os.getenv('KUBERNETES_SERVICE_HOST', '')
KUBERNETES_PORT = os.getenv('KUBERNETES_PORT_443_TCP_PORT', '')
TOKENT_FILE = '/var/run/secrets/kubernetes.io/serviceaccount/token'
NAMESPACE_FILE = '/var/run/secrets/kubernetes.io/serviceaccount/namespace'
KUBERNETES_URL = f'https://{KUBERNETES_SERVICE_HOST}:{KUBERNETES_PORT}'

class GracefulKiller:
    def __init__(self):
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)
        self.kill_now = False

    def exit_gracefully(self, signum, frame):
        self.kill_now = True

class Supervisor(object):
    def getProgramStatus(self, name):
        server = xmlrpc.client.ServerProxy('http://localhost:9001/RPC2')
        info = server.supervisor.getProcessInfo(name)

        if 'statename' in info:
            return info['statename']
        return 'UNKNOWN'

    def startProgram(self, name):
        server = xmlrpc.client.ServerProxy('http://localhost:9001/RPC2')
        return server.supervisor.startProcess(name)

class RedisClusterCreator(object):
    def __init__(self, namespace_file, token_file):
        self.__namespace = self.__get_namespace(namespace_file)
        self.__token = self.__load_token(token_file)
        (self.__myip, self.__myid, self.__myflag) = self.get_myself()

    def __get_namespace(self, namespace_file):
        if os.path.exists(namespace_file):
            with open(namespace_file, mode='r') as infile:
                return infile.read()
        return None

    def __load_token(self, token_file):
        if os.path.exists(token_file):
            with open(token_file, mode='r') as infile:
                return infile.read()
        return None

    def get_deployment(self, deployment):
        response = requests.get(
            url=f'{KUBERNETES_URL}/apis/extensions/v1beta1/namespaces/{self.__namespace}/deployments/{deployment}',
            headers={
                'Authorization': f'Bearer {self.__token}'
            },
            verify=False
        )
        return response.json()

    def list_pods_ip(self, labels):
        list_ip = []

        response = requests.get(
            url=f'{KUBERNETES_URL}/api/v1/namespaces/{self.__namespace}/pods',
            headers={
                'Authorization': f'Bearer {self.__token}'
            },
            verify=False
        )

        response = response.json()

        for pod in response['items']:
            if pod['metadata']['labels']['app'] == labels['app']:
                if 'podIP' in pod['status']:
                    list_ip.append(pod['status']['podIP'])
        return list_ip

    def cluster_nodes(self):
        nodes = {}
        try:
            rediscon = redis.StrictRedis(host='localhost', port=6379)
            cl_nodes = rediscon.execute_command(f'CLUSTER NODES')
            for node in cl_nodes:
                nodes[node.split(':')[0]] = cl_nodes[node]
        except redis.exceptions.ResponseError as err:
            print(f'cluster_nodes: CLUSTER NODES ERROR: {err.args}')
        return nodes
    
    def get_myslots(self):
        try:
            nodes = self.cluster_nodes()
            for node in nodes:
                if 'myself' in nodes[node]['flags']:
                    return nodes[node]['slots']
        except redis.exceptions.ResponseError as err:
            print(f'get_myslots: GET MYSLOTS ERROR: {err.args}')
        return []

    def get_myself(self):
        try:
            nodes = self.cluster_nodes()

            for node in nodes:
                if 'myself' in nodes[node]['flags']:
                    return node, nodes[node]['node_id'], nodes[node]['flags']
        except redis.exceptions.ResponseError as err:
            print(f'get_myself: GET MYSELF ERROR: {err.args}')
        return None, None, None

    def meet_peer(self, peers_ip):
        nodes = self.cluster_nodes()

        try:
            rediscon = redis.StrictRedis(host='localhost', port=6379)
            for ip in peers_ip:
                if ip not in nodes:
                    rediscon.execute_command(f'CLUSTER MEET {ip} 6379')
                    print(f'meet_peer: CLUSTER MEET {ip} SUCCESS')
        except redis.exceptions.ResponseError as err:
            print(f'meet_peer: CLUSTER MEET {ip} ERROR: {err.args}')

    def spread_slots(self, peers_ip):
        total_slots = 16384
        slots = 0
        count_masters = int(len(peers_ip) / 2)
        step = total_slots / count_masters
        masters_ip = []

        for ip in range(0, count_masters):
            generated_slots = ''
            for i in range(int(slots), int(slots + step)):
                generated_slots += str(i) + ' '

            masters_ip.append(peers_ip[ip])
            rediscon = redis.StrictRedis(host=peers_ip[ip], port=6379)
            try:
                rediscon.execute_command(f'CLUSTER ADDSLOTS {generated_slots}')
                print(f'spread_slots: CLUSTER ADDSLOTS SUCCESS: {peers_ip[ip]}')
            except redis.exceptions.ResponseError as err:
                print(f'spread_slots: CLUSTER ADDSLOTS ERROR: {err.args}')
            slots += step
        return masters_ip

    def adjust_slaves(self):
        masters = {}

        try:
            rediscon = redis.StrictRedis(host='localhost', port=6379)
            slots = rediscon.execute_command(f'CLUSTER SLOTS')
            for slot in slots:
                ip = slot[2][0].decode('utf-8')
                id = slot[2][2].decode('utf-8')

                if self.__myid == id:
                    print(f'adjust_slaves: I AM A MASTER. EXIT.')
                    return masters

                if id and ip:
                    slaves = []
                    for i in range(3, len(slot)):
                        if self.__myid == slot[i][2].decode('utf-8'):
                            print(f'adjust_slaves: I AM ALREADY SLAVE OF {id}. EXIT.')
                            return self.__myid
                        slaves.append(slot[i])
                    masters[id] = len(slaves)

            s_masters = sorted(masters, key=masters.get)

            if s_masters:
                print(f'adjust_slaves: CLUSTER REPLICATE {s_masters[0]}')
                return rediscon.execute_command(f'CLUSTER REPLICATE {s_masters[0]}')
            else:
                print(f'adjust_slaves: NO MASTERS FOUND')
        except redis.exceptions.ResponseError as err:
            print(f'adjust_slaves: CLUSTER REPLICATE {s_masters[0]} ERROR: {err.args}')
        return masters

    def forget_failed(self):
        rediscon = redis.StrictRedis(host='localhost', port=6379)
        nodes = rediscon.execute_command(f'CLUSTER NODES')
        
        for node in nodes:
            if 'fail' in nodes[node]['flags']:
                print(f"FORGET FAILED NODE {nodes[node]['node_id']}.")
                rediscon.execute_command(f"CLUSTER FORGET {nodes[node]['node_id']}")
                    
parser = argparse.ArgumentParser(usage = '%(prog)s [options]')
parser.add_argument('--build', help='Build cluster', action='store_true')

args = parser.parse_args()

if not args.build:
    parser.print_help()
    sys.exit(-1)

clustercreator = RedisClusterCreator(NAMESPACE_FILE, TOKENT_FILE)
supervisorctl = Supervisor()
killer = GracefulKiller()

while supervisorctl.getProgramStatus('redis-server') != 'RUNNING':
    if killer.kill_now:
        print("TERM SIGNAL RECEIVED. QUIT.")
        break
    time.sleep(1)

print("REDIS SERVER STARTED.")

if args.build:
    peers_ip = []
    methadata = clustercreator.get_deployment('redis')
    peers_ip = clustercreator.list_pods_ip(methadata['metadata']['labels'])

    while len(peers_ip) != int(methadata['spec']['replicas']):
        if killer.kill_now:
            print("TERM SIGNAL RECEIVED. QUIT..")
            break

        peers_ip = clustercreator.list_pods_ip(methadata['metadata']['labels'])
        time.sleep(2)

    print("ALL PODS STARTED.")

    (myip, myid, myflag) = clustercreator.get_myself()
    clustercreator.meet_peer(peers_ip)
    clustercreator.spread_slots(peers_ip)
    time.sleep(3)
    clustercreator.adjust_slaves()

    while True:
        clustercreator.forget_failed()
        time.sleep(2)
