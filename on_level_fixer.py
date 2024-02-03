#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio
import json
import os
import traceback
from typing import cast, Optional

import aiomqtt

DECIDE_AFTER = float(os.environ.get("DECIDE_AFTER", "1"))  # seconds


class LightFixer:
    light_name: str
    client: aiomqtt.Client
    last_on_level: Optional[str]
    set_on_level_task: Optional[asyncio.Task]
    decide_at: float

    def __init__(self, light_name: str, client: aiomqtt.Client):
        self.light_name = light_name
        self.client = client
        self.loop = asyncio.get_running_loop()
        self.last_on_level = None
        self.task = None
        self.loop = asyncio.get_running_loop()
        self.decide_at = 0

    @staticmethod
    def is_light(json_message: dict) -> bool:
        return (
            "level_config" in json_message
            and "on_level" in json_message["level_config"]
        )

    async def set_on_level_task(self):
        while self.loop.time() < self.decide_at:
            await asyncio.sleep(self.decide_at - self.loop.time())
        self.task = None

        if self.last_on_level != "previous":
            await self.client.publish(
                f"zigbee2mqtt/{self.light_name}/1/set",
                payload='{"write":{"cluster":"genLevelCtrl","options":{},"payload":{"onLevel":255}}}',
            )
            print(f"Reset onLevel of {self.light_name} to 'previous'")

    async def handle_message(self, json_payload: dict):
        if "level_config" not in json_payload:
            return

        level_config = json_payload["level_config"]
        if "on_level" not in level_config:
            return

        self.last_on_level = level_config["on_level"]

        now = self.loop.time()
        self.decide_at = now + DECIDE_AFTER

        if self.task is None:
            self.task = self.loop.create_task(self.set_on_level_task())


async def main():
    async with aiomqtt.Client(
        os.environ["MQTT_HOST"], int(os.environ.get("MQTT_PORT", 1883))
    ) as client:
        lights = {}
        await client.subscribe("zigbee2mqtt/+")

        async for message in client.messages:
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
                if name not in lights:
                    lights[name] = LightFixer(name, client)
                    print(f"Learned about new light {name}, setting onLevel")
                    await lights[name].set_on_level_task()

                await lights[name].handle_message(j)


if __name__ == "__main__":
    asyncio.run(main())
