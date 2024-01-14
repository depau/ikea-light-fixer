#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio
import json
import os
import traceback
from typing import cast

import aiomqtt


class LightFixer:
    light_name: str
    client: aiomqtt.Client

    def __init__(self, light_name: str, client: aiomqtt.Client):
        self.light_name = light_name
        self.client = client
        self.loop = asyncio.get_running_loop()

    @staticmethod
    def is_light(json_message: dict) -> bool:
        return "level_config" in json_message and "on_level" in json_message["level_config"]

    async def set_on_level(self):
        await self.client.publish(
            f"zigbee2mqtt/{self.light_name}/1/set",
            payload='{"write":{"cluster":"genLevelCtrl","options":{},"payload":{"onLevel":255}}}',
        )

    async def handle_message(self, json_payload: dict):
        if "level_config" not in json_payload:
            return

        level_config = json_payload["level_config"]
        if "on_level" not in level_config:
            return

        on_level = level_config["on_level"]

        if on_level != "previous":
            await self.set_on_level()
            print(f"Reset onLevel of {self.light_name} to 'previous'")


async def main():
    async with aiomqtt.Client(
        os.environ["MQTT_HOST"], int(os.environ.get("MQTT_PORT", 1883))
    ) as client:
        lights = {}

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
                    if name not in lights:
                        lights[name] = LightFixer(name, client)
                        print(f"Learned about new light {name}, setting onLevel")
                        await lights[name].set_on_level()

                    await lights[name].handle_message(j)


if __name__ == "__main__":
    asyncio.run(main())
