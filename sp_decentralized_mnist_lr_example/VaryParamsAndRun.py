import yaml
import subprocess
from multiprocessing import Process
import pynvml
import os
import argparse 
from multiprocessing import Semaphore
import torch
import time

current_file = os.path.abspath(__file__)
curr_dir = os.path.dirname(current_file)
os.chdir(curr_dir)
os.environ['CUDA_VISIBLE_DEVICES'] = '0,1,2,3'
datasets = ["CIFAR100", "CIFAR10"]
learning_rates = [0.02, 0.002, 0.0005] 
comm_rounds = [500]
# seeds = [3087732978, 918854724, 2152041540, 548193746, 993522575, 1531166731, 3136455588, 3525945833, 2018934764, 1770634816]
seeds = [993522575]
server_optims = ["FedAvg"]


def run_federation_with_semaphore(semaphore, beta, dataset, lr, optim, gpu_id):
    epochs = 4
    server_optim = False if optim == "FedAvg" else True
    run_name = f"Dir:{beta}_Dataset:{dataset}_lr:{lr}_optim:{optim}"
    try:
        run_federation(beta, dataset, lr, optim, run_name, server_optim, gpu_id)
    finally:
        # Release the semaphore when the process is done
        if os.path.exists(os.path.join(curr_dir, f'config/{run_name}.yaml')):
            os.remove(os.path.join(curr_dir, f'config/{run_name}.yaml'))
        semaphore.release()
        
def run_federation(beta, dataset, lr, optim, run_name, server_optim, gpu_id):
    # Path to your YAML configuration and run file
    
    
    write_config_path = os.path.join(curr_dir, f'config/{run_name}.yaml')
    file_to_run = "main.py"
    read_config_path = os.path.join(curr_dir, 'config/fedml_config.yaml')
    
    torch.cuda.set_device(int(gpu_id))
     # Load the configuration
    with open(read_config_path, 'r') as f:
        config = yaml.safe_load(f)
        
    # Modify the configuration
    config['train_args']['server_lr'] = lr
    config['train_args']['server_optim'] = server_optim
    config['train_args']['server_optimizer'] = optim
    config['data_args']['dataset'] = dataset
    config['common_args']['alpha_dirichlet'] = beta
    config['device_args']['gpu_id'] = gpu_id
    config['tracking_args']['run_name'] = run_name
    
    # Save the modified configuration
    with open(write_config_path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False)
    
    env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(gpu_id))
    # Execute main.py
    result = subprocess.run(['python', file_to_run, '--cf', write_config_path], env=env, stderr=subprocess.PIPE)
    if result.returncode !=0:
        print("***********************************************Error message:****************************************************")
        print(f" {result.stderr} ")
        print("************************************************************************************************************")
        print(f"Error for beta: {beta}, dataset: {dataset}, lr: {lr}, , optim: {optim}")
        print("************************************************************************************************************")

def check_gpu_memory(gpu_id, required_memory = 1024*1024*1024):
    pynvml.nvmlInit()
    handle = pynvml.nvmlDeviceGetHandleByIndex(gpu_id)
    info = pynvml.nvmlDeviceGetMemoryInfo(handle)
    pynvml.nvmlShutdown()
    return info.free >= required_memory
                

def update_and_run_config(gpu_id, beta):
    max_processes = 50
    semaphore = Semaphore(max_processes)  # Controls the number of active processes
    processes = []    
    for dataset in datasets:
        for lr in learning_rates:
            for optim in server_optims:
            # for seed in seeds:                                
                # Wait if the number of active processes reaches the limit
                semaphore.acquire()
                while not check_gpu_memory(gpu_id):
                    time.sleep(120)

                p = Process(target=run_federation_with_semaphore, args=(semaphore, beta, dataset, lr, optim, gpu_id))
                processes.append(p)
                p.start()
                time.sleep(200)

    for p in processes:
        p.join()
                

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run federation for a specific GPU')
    parser.add_argument('--gpu_id', type=int, required=True, help='GPU id to use (0, 1, 2, 3)')
    parser.add_argument('--beta', type=float, required=True, help='betas = [1.0, 100.0, 0.5, 0.1]')
    args = parser.parse_args()
    update_and_run_config(args.gpu_id, args.beta)
