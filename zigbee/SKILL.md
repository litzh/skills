# Zigbee Device Control Skill

This skill controls Zigbee devices via Zigbee2MQTT using `zigbee.py`.

## Prerequisites

Set environment variables (or pass as CLI arguments):

```bash
export ZIGBEE_BROKER=<mqtt_broker_ip>   # required
export ZIGBEE_DEVICE=<friendly_name>    # required for most commands
export ZIGBEE_PORT=1883                 # optional, default 1883
```

Or pass inline:

```bash
uv run zigbee.py --broker <ip> --device <name> <command>
```

## Workflow

### Step 1: Check device capabilities

```bash
uv run zigbee.py info
```

If the device exists in cache, this prints its model, vendor, and full capability list. Proceed to Step 3.

### Step 2: Device not in cache — run scan

If `info` exits with "No device cache found" or "device not in cache":

```bash
uv run zigbee.py scan
```

This fetches all devices from `zigbee2mqtt/bridge/devices`, saves them to `.devices.json` in the current directory, and prints discovered devices. Then retry `info`.

To list all cached devices without scanning:

```bash
uv run zigbee.py scan --list
```

### Step 3: Send commands based on capabilities

Only send commands the device actually supports (confirmed via `info`).

**state** — on / off / toggle:
```bash
uv run zigbee.py on
uv run zigbee.py off
uv run zigbee.py toggle
```

**brightness** — value 0-254 or percentage:
```bash
uv run zigbee.py brightness 128
uv run zigbee.py brightness 50%
```

**color_temp** — mired value, percentage, or preset name:
```bash
uv run zigbee.py temp 300
uv run zigbee.py temp 50%
uv run zigbee.py temp warm      # presets: coolest, cool, neutral, warm, warmest
```

**color** — hex or R,G,B recommended; x/y (CIE 1931) also accepted:
```bash
uv run zigbee.py color "#FF5500"
uv run zigbee.py color 255,85,0
uv run zigbee.py color x:0.3,y:0.4
```

Note: the device's native color space is CIE 1931 xy. Zigbee2MQTT converts hex/RGB to xy internally, so hex or RGB is the preferred input format. When reading state via `get`, the color is reported back in xy format.

**effect** — trigger a light effect:
```bash
uv run zigbee.py effect colorloop
uv run zigbee.py effect stop_colorloop
# valid values listed in `info` output
```

**do_not_disturb** — keep light OFF after power outage:
```bash
uv run zigbee.py dnd on
uv run zigbee.py dnd off
```

**color_power_on_behavior** — behavior on power restore:
```bash
uv run zigbee.py poweron previous    # initial / previous / customized
```

**set** — send multiple properties in one command:
```bash
uv run zigbee.py set --state on --brightness 80% --temp warm --transition 2
uv run zigbee.py set --state on --on-time 300    # auto-off after 300s
```

**get** — read current device state:
```bash
uv run zigbee.py get                        # all fields
uv run zigbee.py get state brightness       # specific fields
```

## Notes

- Always check `info` before sending commands — do not assume capabilities.
- `effect` and `color` commands will error if the device does not support them.
- Percentages are scaled to the device's actual min/max range from cache.
- `--transition` (seconds) can be added to `brightness`, `temp`, `color`, and `set` for smooth transitions.
- The cache file `.devices.json` is local to the working directory. Run `scan` again if devices are added or renamed in Zigbee2MQTT.
