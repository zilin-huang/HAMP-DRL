import copy

from haim_drl.utils.callback import HAIM_DRLCallbacks
from haim_drl.utils.config import baseline_eval_config
from haim_drl.utils.human_in_the_loop_env import HumanInTheLoopEnv
from haim_drl.utils.train import train
from haim_drl.utils.train_utils import get_train_parser
from ray.rllib.agents.ppo.ppo import PPOTrainer

evaluation_config = {"env_config": copy.deepcopy(baseline_eval_config)}

if __name__ == '__main__':
    args = get_train_parser().parse_args()

    exp_name = args.exp_name or "PPO"
    stop = {"timesteps_total": 1000_000}

    config = dict(
        env=HumanInTheLoopEnv,
        env_config=dict(
            main_exp=False
        ),

        # ===== Evaluation =====
        evaluation_interval=1,
        evaluation_num_episodes=30,
        evaluation_config=evaluation_config,
        evaluation_num_workers=2,
        metrics_smoothing_episodes=30,

        # ===== Training =====
        horizon=1500,
        num_sgd_iter=20,
        lr=5e-5,
        grad_clip=10.0,
        rollout_fragment_length=200,
        sgd_minibatch_size=100,
        train_batch_size=4000,
        num_gpus=0.2 if args.num_gpus != 0 else 0,
        num_cpus_per_worker=0.1,
        num_cpus_for_driver=0.5,
        num_workers=8,
        clip_actions=False
    )

    train(
        PPOTrainer,
        exp_name=exp_name,
        keep_checkpoints_num=5,
        stop=stop,
        config=config,
        num_gpus=args.num_gpus,
        num_seeds=5,
        custom_callback=HAIM_DRLCallbacks,
        # test_mode=True,
        # local_mode=True
    )
