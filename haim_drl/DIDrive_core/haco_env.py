# import evdev
import gym
import numpy as np
import pygame
from easydict import EasyDict
# from evdev import ecodes, InputDevice

from haim_drl.DIDrive_core.envs.simple_carla_env import SimpleCarlaEnv
from haim_drl.DIDrive_core.demo.simple_rl.env_wrapper import ContinuousBenchmarkEnvWrapper
from haim_drl.DIDrive_core.demo.simple_rl.sac_train import compile_config


def safe_clip(array, min_val, max_val):
    array = np.nan_to_num(array.astype(np.float64), copy=False, nan=0.0, posinf=max_val, neginf=min_val)
    return np.clip(array, min_val, max_val).astype(np.float64)


train_config = dict(
    env=dict(
        collector_env_num=1,
        evaluator_env_num=0,
        simulator=dict(
            town='Town01',
            disable_two_wheels=True,
            verbose=False,
            waypoint_num=32,
            planner=dict(
                type='behavior',
                resolution=1,
            ),
            obs=(
                dict(
                    name='rgb',
                    type='rgb',
                    size=[1600, 800],
                    position=[-5.5, 0, 2.8],
                    rotation=[-15, 0, 0],
                ),
                dict(
                    name='birdview',
                    type='bev',
                    size=[42, 42],
                    pixels_per_meter=2,
                    pixels_ahead_vehicle=16,
                ),
                # dict(
                #     name='birdview',
                #     type='bev',
                #     size=[32, 32],
                #     pixels_per_meter=1,
                #     pixels_ahead_vehicle=14,
                # ),
            )
        ),
        col_is_failure=True,
        stuck_is_failure=False,
        wrong_direction_is_failure=False,
        off_route_is_failure=False,
        off_road_is_failure=True,
        ignore_light=True,
        visualize=dict(
            type='rgb',
            outputs=['show']
        ),
        manager=dict(
            collect=dict(
                auto_reset=True,
                shared_memory=False,
                context='spawn',
                max_retry=1,
            ),
            eval=dict()
        ),
        wrapper=dict(
            # Collect and eval suites for training
            collect=dict(suite='train_ft'),

        ),
    ),
)


class SteeringWheelController:
    RIGHT_SHIFT_PADDLE = 4
    LEFT_SHIFT_PADDLE = 5
    STEERING_MAKEUP = 1.5

    def __init__(self):
        pygame.display.init()
        pygame.joystick.init()
        assert pygame.joystick.get_count() > 0, "Please connect joystick or use keyboard input"
        print("Successfully Connect your Joystick!")

        # ffb_device = evdev.list_devices()[0]
        # self.ffb_dev = InputDevice(ffb_device)

        self.joystick = pygame.joystick.Joystick(0)
        self.joystick.init()

        self.right_shift_paddle = False
        self.left_shift_paddle = False

        self.button_circle = False
        self.button_rectangle = False
        self.button_triangle = False
        self.button_x = False

        self.button_up = False
        self.button_down = False
        self.button_right = False
        self.button_left = False

    def process_input(self, speed):
        pygame.event.pump()
        steering = -self.joystick.get_axis(0)
        throttle = (1 - self.joystick.get_axis(1)) / 2
        brake = (1 - self.joystick.get_axis(3)) / 2
        offset = 30
        # val = int(65535 * (speed + offset) / (120 + offset))
        # self.ffb_dev.write(ecodes.EV_FF, ecodes.FF_AUTOCENTER, val)
        self.right_shift_paddle = True if self.joystick.get_button(self.RIGHT_SHIFT_PADDLE) else False
        self.left_shift_paddle = True if self.joystick.get_button(self.LEFT_SHIFT_PADDLE) else False

        self.left_shift_paddle = True if self.joystick.get_button(self.LEFT_SHIFT_PADDLE) else False
        self.left_shift_paddle = True if self.joystick.get_button(self.LEFT_SHIFT_PADDLE) else False

        self.button_circle = True if self.joystick.get_button(2) else False
        self.button_rectangle = True if self.joystick.get_button(1) else False
        self.button_triangle = True if self.joystick.get_button(3) else False
        self.button_x = True if self.joystick.get_button(0) else False

        hat = self.joystick.get_hat(0)
        self.button_up = True if hat[-1] == 1 else False
        self.button_down = True if hat[-1] == -1 else False
        self.button_left = True if hat[0] == -1 else False
        self.button_right = True if hat[0] == 1 else False

        return [-steering * self.STEERING_MAKEUP, (throttle - brake)]

    def reset(self):
        pass


class KeyboardController:
    STEERING_INCREMENT = 0.02
    STEERING_DECAY = 0.2

    THROTTLE_INCREMENT = 0.01
    THROTTLE_DECAY = 0.05

    BRAKE_INCREMENT = 0.01
    BRAKE_DECAY = 0.05

    def __init__(self, pygame_control=True):
        assert pygame_control
        self.pygame_control = pygame_control
        pygame.init()
        pygame.display.init()
        pygame.joystick.init()
        self.steering = 0.
        self.throttle_brake = 0.

        self.last_press = {"w":False, "s":False, "a":False, "d":False}
        self.np_random = np.random.RandomState(None)

    def process_input(self, vehicle):
        if self.last_press["a"]:
            steering= -1
        elif self.last_press["d"]:
            steering=1
        else:
            steering =0

        if self.last_press["w"]:
            throttle_brake = 1
        elif self.last_press["s"]:
            throttle_brake = -1
        else:
            throttle_brake = 0

        for event in pygame.event.get():
            if event.type == pygame.KEYDOWN and event.key == pygame.K_w:
                throttle_brake=1.
                self.last_press["w"]=True
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_s:
                throttle_brake=-1.
                self.last_press["s"]=True
            if event.type == pygame.KEYDOWN and event.key == pygame.K_a:
                steering = -1
                self.last_press["a"] = True
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_d:
                steering = 1.
                self.last_press["d"] = True

            if event.type == pygame.KEYUP and event.key == pygame.K_w:
                throttle_brake=0.
                self.last_press["w"]=False
            elif event.type == pygame.KEYUP and event.key == pygame.K_s:
                throttle_brake=0
                self.last_press["s"]=False
            if event.type == pygame.KEYUP and event.key == pygame.K_a:
                steering = 0
                self.last_press["a"] = False
            elif event.type == pygame.KEYUP and event.key == pygame.K_d:
                steering = 0.
                self.last_press["d"] = False

        self.further_process(steering, throttle_brake)
        return np.array([self.steering, self.throttle_brake], dtype=np.float64)

    def further_process(self, steering, throttle_brake):
        if steering == 0.:
            if self.steering > 0.:
                self.steering -= self.STEERING_DECAY
                self.steering = max(0., self.steering)
            elif self.steering < 0.:
                self.steering += self.STEERING_DECAY
                self.steering = min(0., self.steering)
        if throttle_brake == 0.:
            if self.throttle_brake > 0.:
                self.throttle_brake -= self.THROTTLE_DECAY
                self.throttle_brake = max(self.throttle_brake, 0.)
            elif self.throttle_brake < 0.:
                self.throttle_brake += self.BRAKE_DECAY
                self.throttle_brake = min(0., self.throttle_brake)

        if steering > 0.:
            self.steering += self.STEERING_INCREMENT if self.steering > 0. else self.STEERING_DECAY
        elif steering < 0.:
            self.steering -= self.STEERING_INCREMENT if self.steering < 0. else self.STEERING_DECAY

        if throttle_brake > 0.:
            self.throttle_brake += self.THROTTLE_INCREMENT
        elif throttle_brake < 0.:
            self.throttle_brake -= self.BRAKE_INCREMENT

        rand = self.np_random.rand(2, 1) / 10000
        # self.throttle_brake += rand[0]
        self.steering += rand[1]

        self.throttle_brake = min(max(-1., self.throttle_brake), 1.)
        self.steering = min(max(-1., self.steering), 1.)

    def reset(self):
        self.steering = 0
        self.throttle_brake=0.

class HACOEnv(ContinuousBenchmarkEnvWrapper):
    def __init__(self, config=None, eval=False, port=9000):
        self.keyboard_control=config.get("keyboard_control", False)
        main_config = EasyDict(train_config)
        self.eval = eval
        if eval:
            train_config["env"]["wrapper"]["collect"]["suite"] = 'FullTown02-v1'
        cfg = compile_config(main_config)
        super(HACOEnv, self).__init__(SimpleCarlaEnv(cfg.env, "localhost", port, None), cfg.env.wrapper.collect)
        self.controller = (SteeringWheelController() if not self.keyboard_control else KeyboardController()) if not eval else None
        self.last_takeover = False
        self.total_takeover_cost = 0
        self.episode_reward = 0

    def step(self, action):
        if self.controller is not None:
            human_action = self.controller.process_input(self.env._simulator_databuffer['state']['speed'] * 3.6)
            if not self.keyboard_control:
                takeover = self.controller.left_shift_paddle or self.controller.right_shift_paddle
            else:
                takeover = True if any(list(self.controller.last_press.values())) else False
        else:
            human_action = [0, 0]
            takeover = False
        o, r, d, info = super(HACOEnv, self).step(human_action if takeover else action)
        self.episode_reward += r
        if not self.last_takeover and takeover:
            cost = self.get_takeover_cost(human_action, action)
            self.total_takeover_cost += cost
            info["takeover_cost"] = cost
        else:
            info["takeover_cost"] = 0

        info["takeover"] = takeover
        info["total_takeover_cost"] = self.total_takeover_cost
        info["raw_action"] = action if not takeover else human_action
        self.last_takeover = takeover

        info["velocity"] = self.env._simulator_databuffer['state']['speed']
        info["steering"] = info["raw_action"][0]
        info["acceleration"] = info["raw_action"][1]
        info["step_reward"] = r
        info["cost"] = self.native_cost(info)
        info["native_cost"] = info["cost"]
        info["out_of_road"] = info["off_road"]
        info["crash"] = info["collided"]
        info["arrive_dest"] = info["success"]
        info["episode_length"] = info["tick"]
        info["episode_reward"] = self.episode_reward
        if not self.eval:
            self.render()
        return o, r[0], d, info

    def native_cost(self, info):
        if info["off_route"] or info["off_road"] or info["collided"] or info["wrong_direction"]:
            return 1
        else:
            return 0

    def get_takeover_cost(self, human_action, agent_action):
        takeover_action = safe_clip(np.array(human_action), -1, 1)
        agent_action = safe_clip(np.array(agent_action), -1, 1)
        # cos_dist = (agent_action[0] * takeover_action[0] + agent_action[1] * takeover_action[1]) / 1e-6 +(
        #         np.linalg.norm(takeover_action) * np.linalg.norm(agent_action))

        multiplier = (agent_action[0] * takeover_action[0] + agent_action[1] * takeover_action[1])
        divident = np.linalg.norm(takeover_action) * np.linalg.norm(agent_action)
        if divident < 1e-6:
            cos_dist = 1.0
        else:
            cos_dist = multiplier / divident
        return 1 - cos_dist

    def reset(self, *args, **kwargs):
        self.last_takeover = False
        self.total_takeover_cost = 0
        self.episode_reward = 0
        self.controller.reset()
        return super(HACOEnv, self).reset()

    @property
    def action_space(self):
        return gym.spaces.Box(-1.0, 1.0, shape=(2,))

    @property
    def observation_space(self):
        return gym.spaces.Dict({"birdview": gym.spaces.Box(low=0, high=1, shape=(42, 42, 5), dtype=np.uint8),
                                "speed": gym.spaces.Box(-10., 10.0, shape=(1,))})


if __name__ == "__main__":
    env = HACOEnv(config={"keyboard_control":True})
    o = env.reset()

    while True:
        if not env.observation_space.contains(o):
            print(o)
        o, r, d, i = env.step([0., -0.0])

        if d:
            env.reset()
