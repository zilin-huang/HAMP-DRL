from __future__ import print_function

from haim_drl.algo.IWR.exp_saver import Experiment
from haim_drl.algo.IWR.model import Ensemble
from haim_drl.algo.IWR.utils import *
from haim_drl.utils.config import baseline_eval_config, baseline_train_config
from haim_drl.utils.human_in_the_loop_env import HumanInTheLoopEnv
from stable_baselines3.common.vec_env.subproc_vec_env import SubprocVecEnv

"""
requirement for IWR/HG-Dagger/GAIl:

create -n haco-iwr python version=3.7
1. pip install loguru imageio easydict tensorboardX pyyaml  stable_baselines3 pickle5
2. conda install pytorch==1.5.0 torchvision==0.6.0 cudatoolkit=9.2 -c pytorch
"""


def IWR_balance_sample(agent_samples, human_samples):
    agent_x = agent_samples["state"]
    agent_y = agent_samples["action"]

    human_x = human_samples["state"]
    human_y = human_samples["action"]

    agent_sample_num = len(agent_y)
    human_sample_num = len(human_y) + 1
    ratio = int(agent_sample_num / human_sample_num)

    # according to the practical experience reported in paper, repeat the human samples to mix in same proportion
    ret_x = agent_x + ratio * human_x
    ret_y = agent_y + ratio * human_y
    return ret_x, ret_y


# hyperpara
BC_WARMUP_DATA_USAGE = 30000  # use human data to do warm up
NUM_ITS = 5
STEP_PER_ITER = 5000
learning_rate = 5e-4
batch_size = 256

need_eval = False  # we do not perform online evaluation. Instead, we evaluate by saved model
evaluation_episode_num = 30
num_sgd_epoch = 1000  # sgd epoch on data set
device = "cuda"

# training env_config/test env config
training_config = baseline_train_config
training_config["use_render"] = True
training_config["manual_control"] = True
eval_config = baseline_eval_config

#
# #########################################################################################
# training_config["controller"] = "keyboard"
# #########################################################################################


if __name__ == "__main__":
    tm = time.localtime(time.time())
    tm_stamp = "%s-%s-%s-%s-%s-%s" % (tm.tm_year, tm.tm_mon, tm.tm_mday, tm.tm_hour, tm.tm_min, tm.tm_sec)
    log_dir = os.path.join(
        "IWR_lr_{}_bs_{}_sgd_iter_{}_iter_batch_{}".format(learning_rate, batch_size, num_sgd_epoch,
                                                           STEP_PER_ITER), tm_stamp)
    exp_log = Experiment()
    exp_log.init(log_dir=log_dir)
    model_save_path = os.path.join(log_dir, "IWR_models")
    os.mkdir(model_save_path)

    training_env = SubprocVecEnv(
        [lambda: HumanInTheLoopEnv(training_config)])  # seperate with eval env to avoid metadrive collapse
    eval_env = HumanInTheLoopEnv(eval_config)
    obs_shape = eval_env.observation_space.shape
    action_shape = eval_env.action_space.shape

    # fill buffer with expert data
    agent_samples = load_human_data('/home/zilin/code/HAIM-DRL/haim_drl/utils/human_traj_100_0.06.json', data_usage=BC_WARMUP_DATA_USAGE)
    human_samples = {"state": [],
                     "action": [],
                     "next_state": [],
                     "reward": [],
                     "terminal": []}

    # train first epoch via human data
    agent = Ensemble(obs_shape, action_shape, device=device).to(device).float()
    X_train, y_train = agent_samples["state"], agent_samples["action"]
    train_model(agent, X_train, y_train,
                os.path.join(model_save_path, "model_{}.pth".format(0)),
                num_epochs=num_sgd_epoch,
                batch_size=batch_size,
                learning_rate=learning_rate,
                exp_log=exp_log)
    if need_eval:
        evaluation(eval_env, agent, evaluation_episode_num=evaluation_episode_num, exp_log=exp_log)
    exp_log.end_iteration(0)

    # count
    for iteration in range(1, NUM_ITS):
        steps = 0
        episode_reward = 0
        success_num = 0
        episode_cost = 0

        disturbance_num = 0
        episode_disturbance_cost = 0

        done_num = 0
        state = training_env.reset()[0]
        # for user friendly :)
        # training_env.env_method("stop")
        # print("Finish training iteration:{}, Press S to Start new iteration".format(iteration - 1))
        sample_start = time.time()

        while True:

            next_state, r, done, info = training_env.step(np.array([agent.act(torch.tensor(state, device=device))]))
            next_state = next_state[0]
            r = r[0]
            done = done[0]
            info = info[0]
            action = info["raw_action"]
            takeover = info["takeover"]

            episode_reward += r
            episode_cost += info["native_cost"]

            disturbance_num += (float(info["disturbance"]))
            episode_disturbance_cost += info["disturbance_cost"]

            if not takeover:
                # for hg dagger aggregate data only when takeover occurs
                agent_samples["state"].append(state)
                agent_samples["action"].append(np.array(action))
                agent_samples["next_state"].append(next_state)
                agent_samples["reward"].append(r)
                agent_samples["terminal"].append(done)
            else:
                human_samples["state"].append(state)
                human_samples["action"].append(np.array(action))
                human_samples["next_state"].append(next_state)
                human_samples["reward"].append(r)
                human_samples["terminal"].append(done)

            state = next_state
            steps += 1

            # train after BATCH_PER_ITER steps
            if done:
                if info["arrive_dest"]:
                    success_num += 1
                done_num += 1
                if steps > STEP_PER_ITER:
                    exp_log.scalar(is_train=True, mean_episode_reward=episode_reward / done_num,
                                   mean_episode_cost=episode_cost / done_num,

                                   mean_episode_disturbance_num=disturbance_num / done_num,
                                   mean_episode_disturbance_cost=episode_disturbance_cost / done_num,

                                   success_rate=success_num / done_num,
                                   mean_step_reward=episode_reward / steps,
                                   sample_time=time.time() - sample_start,
                                   human_samples_size=len(human_samples["state"]),
                                   agent_samples=len(agent_samples["state"]))

                    X_train, y_train = IWR_balance_sample(agent_samples, human_samples)
                    # Create new model
                    agent = Ensemble(obs_shape, action_shape, device=device).to(device).float()
                    train_model(agent, X_train, y_train,
                                os.path.join(model_save_path, "model_{}.pth".format(iteration)),
                                num_epochs=num_sgd_epoch,
                                batch_size=batch_size,
                                learning_rate=learning_rate,
                                exp_log=exp_log)
                    if need_eval:
                        evaluation(eval_env, agent, evaluation_episode_num=evaluation_episode_num, exp_log=exp_log)
                    break
        exp_log.end_iteration(iteration)
    training_env.close()
    eval_env.close()
