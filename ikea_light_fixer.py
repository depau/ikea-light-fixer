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

DECIDE_AFTER = 0.5  # seconds
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


class LightFixer:
    light_name: str
    client: aiomqtt.Client
    history: TimestampDict[LightState]
    decision_task: Optional[asyncio.Task]

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

        if self.decision_task is not None:
            self.decision_task.cancel()

        self.decision_task = self.loop.create_task(self.decide())

    async def decide(self):
        await asyncio.sleep(DECIDE_AFTER)
        self.decision_task = None

        now = self.loop.time()
        cur_state = self.history[now]

        if not cur_state.state:
            return

        if cur_state.brightness <= 1:
            try:
                time = now - 1
                state = self.history[time]

                while state.brightness <= 1:
                    time -= 1
                    state = self.history[time]
                brightness = state.brightness
            except KeyError:
                brightness = 255

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

                try:
                    j = json.loads(message.payload.decode("utf-8"))
                except json.JSONDecodeError:
                    traceback.print_exc()
                    continue

                if LightFixer.is_light(j):
                    lights[name].handle_message(j)


if __name__ == "__main__":
    asyncio.run(main())
