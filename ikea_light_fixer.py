#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import json
import os
import traceback
from collections import defaultdict
from dataclasses import dataclass
from typing import TypeVar, MutableMapping, Optional, cast

import aiomqtt
from sortedcontainers import SortedDict

DECIDE_AFTER = 1  # seconds
MAX_HISTORY_LENGTH = 50  # seconds

T = TypeVar("T")


class TimestampDict(MutableMapping[float, T]):
    def __init__(self, mapping_or_iterable=None):
        self._dict = SortedDict()
        if mapping_or_iterable is not None:
            self.update(mapping_or_iterable)

    def __setitem__(self, key: float, value: T):
        self._dict[key] = value

    def __delitem__(self, key: float):
        del self._dict[key]

    def __getitem__(self, key: float):
        if key in self._dict:
            return self._dict[key]

        lower_bound = self._dict.bisect_left(key)
        if lower_bound == 0:
            raise KeyError(key)
        # noinspection PyUnresolvedReferences
        return self._dict[self._dict.keys()[lower_bound - 1]]

    def __len__(self):
        return len(self._dict)

    def __iter__(self):
        return iter(self._dict)

    def items(self):
        return self._dict.items()

    def values(self):
        return self._dict.values()

    def keys(self):
        return self._dict.keys()

    def __repr__(self):
        return repr(self._dict)

    def __str__(self):
        return str(self._dict)

    def __eq__(self, other):
        if not isinstance(other, TimestampDict):
            return NotImplemented
        return self._dict == other._dict


@dataclass
class LightState:
    state: bool
    brightness: int

    def __eq__(self, __value):
        if not isinstance(__value, LightState):
            return NotImplemented

        if self.state != __value.state:
            return False

        if self.state:
            return self.brightness == __value.brightness

        return True

    def __hash__(self):
        return hash((self.state, self.brightness if self.state else None))


async def max_brightness_last_n_seconds(
    history: TimestampDict[LightState], n_seconds=10
):
    max_brightness = 0
    cumulative_on_time = 0.0
    last_timestamp = asyncio.get_running_loop().time()

    for timestamp, light_state in reversed(history.items()):
        time_diff = last_timestamp - timestamp

        # Only accumulate time when the light is on
        if light_state.state:
            cumulative_on_time += time_diff
            # Update max brightness
            if light_state.brightness > max_brightness:
                max_brightness = light_state.brightness

        # Stop if we have accumulated n_seconds of on-time
        if cumulative_on_time >= n_seconds:
            break

        last_timestamp = timestamp

    if max_brightness <= 1:
        return 255

    return max_brightness


class LightFixer:
    light_name: str
    client: aiomqtt.Client
    history: TimestampDict[LightState]
    decision_task: Optional[asyncio.Task]
    decide_at: float

    def __init__(self, light_name: str, client: aiomqtt.Client):
        self.light_name = light_name
        self.client = client
        self.history = TimestampDict()
        self.decision_task = None
        self.loop = asyncio.get_running_loop()

    @staticmethod
    def is_light(json_message: dict) -> bool:
        return "brightness" in json_message and "state" in json_message

    def handle_message(self, json_message: dict):
        now = self.loop.time()
        last_state = self.history[now] if self.history else None
        state = LightState(
            state=json_message["state"] == "ON",
            brightness=json_message["brightness"],
        )

        if state == last_state:
            return

        print(
            f"Received update for {self.light_name + ':':<30} {state.state and 'ON' or 'OFF':>3}   {state.brightness:>3}"
        )

        self.history[now] = state
        if len(self.history) > MAX_HISTORY_LENGTH:
            del self.history[next(iter(self.history))]

        self.decide_at = now + DECIDE_AFTER

        if self.decision_task is None:
            self.decision_task = self.loop.create_task(self.decide())

    async def decide(self):
        while self.loop.time() < self.decide_at:
            await asyncio.sleep(self.decide_at - self.loop.time())
        self.decision_task = None

        now = self.loop.time()
        cur_state = self.history[now]

        if not cur_state.state:
            return

        if cur_state.brightness <= 1:
            brightness = await max_brightness_last_n_seconds(self.history)

            print(
                f"Rolling back brightness of {self.light_name} to {brightness} (was {cur_state.brightness})"
            )

            await self.client.publish(
                f"zigbee2mqtt/{self.light_name}/set/brightness",
                payload=brightness,
                qos=1,
            )


class LightFixerDict(defaultdict):
    def __init__(self, client: aiomqtt.Client):
        super().__init__()
        self.client = client

    def __missing__(self, key):
        self[key] = LightFixer(key, self.client)
        return self[key]


async def main():
    ignore_list = os.environ.get("IGNORE", "").split(",")

    async with aiomqtt.Client(
        os.environ["MQTT_HOST"], int(os.environ.get("MQTT_PORT", 1883))
    ) as client:
        lights = LightFixerDict(client)

        async with client.messages() as messages:
            await client.subscribe("zigbee2mqtt/+")
            async for message in messages:
                message = cast(aiomqtt.Message, message)
                name = message.topic.value.split("/")[1]

                if name.endswith("_g"):
                    continue  # ignore groups

                if name in ignore_list:
                    continue

                try:
                    j = json.loads(message.payload.decode("utf-8"))
                except json.JSONDecodeError:
                    traceback.print_exc()
                    continue

                if LightFixer.is_light(j):
                    lights[name].handle_message(j)


if __name__ == "__main__":
    asyncio.run(main())
