# IKEA TRÅDFRI light brightness fixer

After 3 years, out of nowhere, my IKEA Zigbee lights decided they will randomly
set their brightness to 1. This happens at random times and when turning them
on. No idea why, no will to go fix it at the source.

## Old script

The old `brightness_fixer.py` script monitors the brightness of the lights via
Zigbee2MQTT and sets it back to the previous value if the lights are on and the
brightness is 1.

## New script

I since discovered that the problem is due to the fact that, on some lights, for
some unknown reason, the `onLevel` attribute of the `genLevelCtrl` cluster is
reset to `0` when reconnecting power to the light, and sometimes even randomly
when the light is on. More
info [here](https://github.com/Koenkk/zigbee2mqtt/issues/19211).

The new `on_level_fixer.py` script implements the workaround
suggested [here](https://github.com/Koenkk/zigbee2mqtt/issues/19211#issuecomment-1871092838)
and it sets the `onLevel` attribute back to `255` (previous value) when the
light
is detected the first time, then automatically when it changes to any other
value `255`.

For this to work you must enable the reporting of the `onLevel` attribute; you
can configure it to something like this:

- Endpoint: `1`
- Cluster: `LevelCtrl`
- Attribute: `onLevel`
- Min rep interval: `60`
- Max rep interval: `300`
- Min rep change: `1`
