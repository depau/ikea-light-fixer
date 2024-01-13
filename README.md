# IKEA TRÅDFRI light brightness fixer

After 3 years, out of nowhere, my IKEA Zigbee lights decided they will randomly
set their brightness to 1. This happens at random times and when turning them
on. No idea why, no will to go fix it at the source.

This script monitors the brightness of the lights via Zigbee2MQTT and sets it
back to the previous value if the lights are on and the brightness is 1.
