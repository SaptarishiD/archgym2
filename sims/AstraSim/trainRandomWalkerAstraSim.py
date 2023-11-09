import json
import time
import random
import pandas as pd
import numpy as np
import envlogger
from arch_gym.envs import AstraSimWrapper, AstraSimEnv
from arch_gym.envs.envHelpers import helpers
from configs import arch_gym_configs
import os
import sys

from absl import flags
from absl import app
from absl import logging

os.sys.path.insert(0, os.path.abspath('../../'))
os.sys.path.insert(0, os.path.abspath('../../arch_gym'))


# define workload in run_general.sh

flags.DEFINE_string('workload', 'resnet18', 'Which AstraSim workload to run?')
flags.DEFINE_integer('num_steps', 50, 'Number of training steps.')
flags.DEFINE_integer('num_episodes', 1, 'Number of training episodes.')
flags.DEFINE_bool('use_envlogger', True, 'Use envlogger to log the data.')
flags.DEFINE_string('traject_dir',
                    'random_walker_trajectories',
                    'Directory to save the dataset.')
flags.DEFINE_string('summary_dir', ".", 'Directory to save the dataset.')
flags.DEFINE_string('reward_formulation', 'latency',
                    'Which reward formulation to use?')
FLAGS = flags.FLAGS


# network: parses the network file
def parse_network(network_file, action_dict):
    with open(network_file) as f:
        network = json.load(f)

        for key in network.keys():
            action_dict['network'][key] = network[key]
    return network


# systems: parse from file into json into generate_random_actions
def parse_system(system_file, action_dict):
    # parse system_file (above is the content) into dict
    action_dict['system'] = {}
    with open(system_file, 'r') as file:
        lines = file.readlines()

        for line in lines:
            key, value = line.strip().split(': ')
            action_dict['system'][key] = value


# parses knobs that we want to experiment with
def parse_knobs(knobs_spec):
    SYSTEM_KNOBS = {}
    NETWORK_KNOBS = {}

    with open(knobs_spec, 'r') as file:
        file_contents = file.read()
        parsed_dicts = {}

        # Evaluate the file contents and store the dictionaries in the parsed_dicts dictionary
        exec(file_contents, parsed_dicts)

        # Access the dictionaries
        SYSTEM_KNOBS = parsed_dicts['SYSTEM_KNOBS']
        NETWORK_KNOBS = parsed_dicts['NETWORK_KNOBS']

    return SYSTEM_KNOBS, NETWORK_KNOBS


# action_type = specify 'network' or 'system
# new_params = parsed knobs from experiment file
def generate_random_actions(action_dict, system_knob, network_knob):
    dicts = [(system_knob, 'system'), (network_knob, 'network')]
    for dict_type, dict_name in dicts:
        for knob in dict_type.keys():
            if isinstance(dict_type[knob], set):
                action_dict[dict_name][knob] = random.choice(
                    list(dict_type[knob]))
            else:
                action_dict[dict_name][knob] = random.randint(
                    dict_type[knob][1], dict_type[knob][2])

    return action_dict

def write_network(dimension):
    def dim_helper(dim, val):
        return [val for _ in range(dim)]

    def rand_dim_helper(dim, vals):
        return [random.choice(vals) for _ in range(dim)]

    links_count = {"Ring": 2, "FullyConnected": 7, "Switch": 1}

    def rand_num_helper(dim, min, max):
        return [random.randint(min, max) for _ in range(dim)]

    def rand_float_helper(dim, min, max):
        return [round(random.uniform(min, max), 1) for _ in range(dim)]

    network = {
        "topology-name": random.choice(["Hierarchical"]),
        "topologies-per-dim": rand_dim_helper(dimension, ["Ring", "FullyConnected", "Switch"]),
        # NEED TO CHECK HOW RANDOM DIM TYPE CAN BE
        "dimension-type": dim_helper(dimension, random.choice(["N", "P"])),
        "dimensions-count": dimension,
        "units-count": rand_num_helper(dimension, 2, 8),
        "link-latency": rand_num_helper(dimension, 1, 500),
        "link-bandwidth": rand_float_helper(dimension, 12.0, 250.0),
        # SHOULD THIS BE ONLY ZEROS?
        "nic-latency": rand_num_helper(dimension, 0, 0),
        "router-latency": rand_num_helper(dimension, 0, 10),
        "hbm-latency": rand_num_helper(dimension, 1, 500),
        "hbm-bandwidth": rand_num_helper(dimension, 1, 500),
        "hbm-scale": rand_num_helper(dimension, 0, 1),
    }

    network["links-count"] = [links_count[network["topologies-per-dim"][i]]
                                for i in range(dimension)]

    return network


def write_system(dimension):
        def implementation_helper(dim, val):
            if val in ["oneRing", "oneDirect"]:
                return val
            else:
                value = ""
                for _ in range(dim):
                    value += val + "_"
                return value[:-1]

        system = {
            "scheduling-policy": random.choice(["LIFO", "FIFO"]),
            "endpoint-delay": random.randint(1, 10),
            "active-chunks-per-dimension": 1,
            # whenever dataset splits is high, it takes a long time to run
            "preferred-dataset-splits": random.randint(1, 32),
            "boost-mode": random.randint(0, 1),
            "all-reduce-implementation": implementation_helper(dimension, random.choice(["ring", "direct", "doubleBinaryTree", "oneRing", "oneDirect"])),
            "all-gather-implementation": implementation_helper(dimension, random.choice(["ring", "direct", "doubleBinaryTree", "oneRing", "oneDirect"])),
            "reduce-scatter-implementation": implementation_helper(dimension, random.choice(["ring", "direct", "doubleBinaryTree", "oneRing", "oneDirect"])),
            "all-to-all-implementation": implementation_helper(dimension, random.choice(["ring", "direct", "doubleBinaryTree", "oneRing", "oneDirect"])),
            "collective-optimization": random.choice(["baseline", "localBWAware"])
        }
        return system


def write_workload():
    value = ""
    # randomize workload type
    workload_type = random.choice(["DATA\n", "HYBRID_TRANSFORMER\n", "HYBRID_DLRM\n", "MICRO\n"])
    # randomize number of DNN layers
    layers_count = random.randint(1, 50)
    if workload_type == "MICRO\n":
        layers_count = 1
    value += workload_type

    value += str(layers_count) + "\n"
    # configure each layer
    for i in range(layers_count):
        # layer name and reserved variable
        value += "layer" + str(i) + "\t-1\t"
        # forward pass compute time
        forward_time = str(random.randint(1, 42000000)) + "\t"
        # forward_time = str(random.randint(1, 4200)) + "\t"
        if workload_type == "MICRO\n":
            forward_time = "5\t"
        value += forward_time

        # forward pass communication type
        forward_type = random.choice(["ALLREDUCE", "ALLGATHER", "ALLTOALL", "NONE"]) + "\t"
        if workload_type == "MICRO\n":
            forward_type = "NONE\t"
        value += forward_type
        # forward pass communication size
        forward_size = "0\t" if forward_type == "NONE\t" else str(random.randint(0, 70000000)) + "\t"
        value += forward_size

        # input grad compute time
        grad_time = str(random.randint(1, 42000000)) + " "

        if workload_type == "MICRO\n":
            grad_time = "5\t"
        value += grad_time
        # input grad communication type
        grad_type = random.choice(["ALLREDUCE", "ALLGATHER", "ALLTOALL", "NONE"]) + "\t"
        if workload_type == "MICRO\n":
            grad_type = "NONE\t"
        value += grad_type
        # input grad communication size
        grad_size = "0\t" if grad_type == "NONE\t" else str(random.randint(0, 70000000)) + "\t"
        value += grad_size

        # weight grad compute time
        weight_time = str(random.randint(1, 42000000)) + "\t"
        # weight_time = str(random.randint(1, 4200)) + "\t"
        if workload_type == "MICRO\n":
            weight_time = "5\t"
        value += weight_time
        # weight grad communication type
        weight_type = random.choice(["ALLREDUCE", "ALLGATHER", "ALLTOALL", "NONE"]) + "\t"
        value += weight_type
        # weight grad communication size
        weight_size = "0\t" if weight_type == "NONE\t" else str(random.randint(0, 70000000)) + "\t"

        value += weight_size
        # delay per entire weight/input/output update after the collective is finished
        value += str(random.randint(5, 5000)) + "\n"
        # value += str(random.randint(5, 50)) + "\n"

    return {"value": value}


def generate_random_actions(dimension):
    action = {}
    action['network'] = write_network(dimension)
    action['system'] = write_system(dimension)
    # action['workload'] = write_workload()
    
    return action


def log_results_to_csv(filename, fitness_dict):
    df = pd.DataFrame([fitness_dict['reward']])
    csvfile = os.path.join(filename, "rewards.csv")
    df.to_csv(csvfile, index=False, header=False, mode='a')

    df = pd.DataFrame([fitness_dict['action']])
    csvfile = os.path.join(filename, "actions.csv")
    df.to_csv(csvfile, index=False, header=False, mode='a')

    df = pd.DataFrame([fitness_dict['obs']])
    csvfile = os.path.join(filename, "observations.csv")
    df.to_csv(csvfile, index=False, header=False, mode='a')


# Random walker then random walker, else use other
def wrap_in_envlogger(env, envlogger_dir):
    metadata = {
        'agent_type': 'RandomWalker',
        'num_steps': FLAGS.num_steps,
        'env_type': type(env).__name__,
    }
    if FLAGS.use_envlogger:
        logging.info('Wrapping environment with EnvironmentLogger...')
        env = envlogger.EnvLogger(env,
                                  data_directory=envlogger_dir,
                                  max_episodes_per_file=1000,
                                  metadata=metadata)
        logging.info('Done wrapping environment with EnvironmentLogger.')
        return env
    else:
        return env


def main(_):
    settings_file_path = os.path.realpath(__file__)
    settings_dir_path = os.path.dirname(settings_file_path)
    proj_root_path = os.path.abspath(settings_dir_path)

    astrasim_archgym = os.path.join(proj_root_path, "astrasim-archgym")

    # TODO: V1 SPEC:
    archgen_v1_knobs = os.path.join(astrasim_archgym, "dse/archgen_v1_knobs")
    knobs_spec = os.path.join(archgen_v1_knobs, "themis_knobs_spec.py")
    networks_folder = os.path.join(archgen_v1_knobs, "templates/network")
    systems_folder = os.path.join(astrasim_archgym, "themis/inputs/system")
    workloads_folder = os.path.join(astrasim_archgym, "themis/inputs/workload")

    # DEFINE NETWORK AND SYSTEM AND WORKLOAD
    network_file = os.path.join(networks_folder, "4d_ring_fc_ring_switch.json")
    system_file = os.path.join(
        systems_folder, "4d_ring_fc_ring_switch_baseline.txt")
    workload_file = "all_reduce/allreduce_0.65.txt"

    exe_path = os.path.join(proj_root_path, "run_general.sh")
    network_config = os.path.join(proj_root_path, "general_network.json")
    system_config = os.path.join(proj_root_path, "general_system.txt")
    workload_config = os.path.join(proj_root_path, "general_workload.txt")

    env = AstraSimWrapper.make_astraSim_env(rl_form='random_walker')
    # env = AstraSimEnv.AstraSimEnv(rl_form='random_walker')

    astrasim_helper = helpers()

    # experiment name
    exp_name = str(FLAGS.workload)+"_num_steps_" + \
        str(FLAGS.num_steps) + "_num_episodes_" + str(FLAGS.num_episodes)
    # append logs to base path
    log_path = os.path.join(
        FLAGS.summary_dir, 'random_walker_logs', FLAGS.reward_formulation, exp_name)
    # get the current working directory and append the exp name
    traject_dir = os.path.join(
        FLAGS.summary_dir, FLAGS.traject_dir, FLAGS.reward_formulation, exp_name)
    # check if log_path exists else create it
    if not os.path.exists(log_path):
        os.makedirs(log_path)
    if FLAGS.use_envlogger:
        if not os.path.exists(traject_dir):
            os.makedirs(traject_dir)
    env = wrap_in_envlogger(env, traject_dir)

    start = time.time()

    step_results = {}

    # INITIATE action dict
    action_dict = {}

    # if path exists, use path, else parse the sub-dict
    action_dict['workload'] = {"path": workload_file}

    # TODO: parse system and network
    parse_system(system_file, action_dict)
    parse_network(network_file, action_dict)

    # TODO: parse knobs (all variables to change in action_dict)
    system_knob, network_knob = parse_knobs(knobs_spec)

    best_reward, best_observation, best_actions = 0.0, 0.0, {}

    for i in range(FLAGS.num_episodes):
        logging.info('Episode %r', i)

        for step in range(FLAGS.num_steps):
            # pass into generate_random_actions(dimension, knobs)
            action_dict = generate_random_actions(
                action_dict, system_knob, network_knob)

            # with open("general_workload.txt", 'w') as file:
            #     file.write(action["workload"]["value"])

            # step_result wrapped in TimeStep object
            step_result = env.step(action)
            step_type, reward, discount, observation = step_result

            step_results['reward'] = [reward]
            step_results['action'] = action
            step_results['obs'] = observation

            if reward and reward > best_reward:
                best_reward = reward
                best_observation = observation
                best_actions = action_dict

            log_results_to_csv(log_path, step_results)

    end = time.time()

    print("Best Reward: ", best_reward)
    print("Best Observation: ", best_observation)
    print("Best Parameters: ", best_actions)
    print("Total Time Taken: ", end - start)
    print("Total Useful Steps: ", env.useful_counter)


if __name__ == '__main__':
    app.run(main)