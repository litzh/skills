import json
import os
import sys
import time
from pathlib import Path

import click
import paho.mqtt.client as mqtt
import paho.mqtt.publish as publish


_data_dir = Path(os.environ.get("ZIGBEE_DATA_DIR", Path.home() / ".local/share/zigbee"))
CACHE_FILE = _data_dir / "devices.json"


# ---------------------------------------------------------------------------
# MQTT helpers
# ---------------------------------------------------------------------------

def mqtt_fetch_once(broker, port, topic):
    """Subscribe to a topic and return the first message payload as parsed JSON."""
    received = []

    def on_connect(client, userdata, flags, rc, properties=None):
        client.subscribe(topic)

    def on_message(client, userdata, msg):
        try:
            received.append(json.loads(msg.payload))
        except Exception:
            pass
        client.disconnect()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(broker, port, keepalive=10)
    client.loop_start()

    start = time.time()
    while not received and (time.time() - start) < 5:
        time.sleep(0.1)

    client.loop_stop()
    client.disconnect()
    return received[0] if received else None


def mqtt_get_state(broker, port, friendly_name):
    """Request and return device state as parsed JSON dict."""
    received = []

    def on_connect(client, userdata, flags, rc, properties=None):
        client.subscribe(f"zigbee2mqtt/{friendly_name}")
        client.publish(
            f"zigbee2mqtt/{friendly_name}/get",
            json.dumps({"state": "", "brightness": "", "color_temp": "", "color": {"x": "", "y": ""}}),
        )

    def on_message(client, userdata, msg):
        try:
            received.append(json.loads(msg.payload))
        except Exception:
            pass
        client.disconnect()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(broker, port, keepalive=10)
    client.loop_start()

    start = time.time()
    while not received and (time.time() - start) < 5:
        time.sleep(0.1)

    client.loop_stop()
    client.disconnect()
    return received[0] if received else None


def mqtt_send(broker, port, friendly_name, payload):
    publish.single(
        f"zigbee2mqtt/{friendly_name}/set",
        payload=json.dumps(payload),
        hostname=broker,
        port=port,
    )


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def load_cache():
    if not CACHE_FILE.exists():
        return None
    with open(CACHE_FILE) as f:
        return json.load(f)


def save_cache(devices):
    with open(CACHE_FILE, "w") as f:
        json.dump(devices, f, indent=2)


def require_cache():
    cache = load_cache()
    if cache is None:
        click.echo("No device cache found. Run 'bulb scan' first.", err=True)
        sys.exit(1)
    return cache


def get_device_info(cache, device_name):
    if device_name not in cache:
        available = ", ".join(cache.keys())
        click.echo(f"Error: device '{device_name}' not in cache. Available: {available}", err=True)
        sys.exit(1)
    return cache[device_name]


# ---------------------------------------------------------------------------
# Exposes parser
# ---------------------------------------------------------------------------

def parse_exposes(exposes_list):
    """Extract a flat capability dict from zigbee2mqtt exposes list."""
    caps = {}
    for expose in exposes_list:
        if expose["type"] == "light":
            for feature in expose.get("features", []):
                name = feature["name"]
                if name == "brightness":
                    caps["brightness"] = {"min": feature["value_min"], "max": feature["value_max"]}
                elif name == "color_temp":
                    caps["color_temp"] = {
                        "min": feature["value_min"],
                        "max": feature["value_max"],
                        "presets": [p["name"] for p in feature.get("presets", [])],
                    }
                elif name == "color_xy":
                    caps["color"] = True
                elif name == "state":
                    caps["state"] = True
        elif expose["type"] == "enum" and expose["name"] == "effect":
            caps["effect"] = expose["values"]
        elif expose["name"] == "do_not_disturb":
            caps["do_not_disturb"] = True
        elif expose["name"] == "color_power_on_behavior":
            caps["color_power_on_behavior"] = expose["values"]
    return caps


# ---------------------------------------------------------------------------
# Value conversion
# ---------------------------------------------------------------------------

def parse_percent_or_value(value_str, min_val, max_val):
    s = value_str.strip()
    if s.endswith("%"):
        pct = float(s[:-1]) / 100.0
        return round(min_val + pct * (max_val - min_val))
    return int(s)


def value_to_percent(value, min_val, max_val):
    if max_val == min_val:
        return 0
    return round((value - min_val) / (max_val - min_val) * 100)


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def format_state(state_dict, caps, fields=None):
    lines = []

    def show(key):
        return fields is None or key in fields

    if show("state") and "state" in state_dict:
        lines.append(f"State:      {state_dict['state']}")

    if show("brightness") and "brightness" in state_dict:
        val = state_dict["brightness"]
        b = caps.get("brightness", {"min": 0, "max": 254})
        pct = value_to_percent(val, b["min"], b["max"])
        lines.append(f"Brightness: {val} ({pct}%)")

    if show("color_temp") and "color_temp" in state_dict:
        val = state_dict["color_temp"]
        ct = caps.get("color_temp", {"min": 153, "max": 500})
        pct = value_to_percent(val, ct["min"], ct["max"])
        lines.append(f"Color temp: {val} mired ({pct}%)")

    if show("color") and "color" in state_dict:
        color = state_dict["color"]
        lines.append(f"Color:      x={color.get('x', '?')}, y={color.get('y', '?')}")

    if not lines:
        lines.append(json.dumps(state_dict, indent=2))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.group()
@click.option("--broker", "-b", envvar="ZIGBEE_BROKER", default=None, help="MQTT broker address (or set ZIGBEE_BROKER)")
@click.option("--port", "-p", envvar="ZIGBEE_PORT", default=1883, show_default=True, type=int)
@click.option("--device", "-d", envvar="ZIGBEE_DEVICE", default=None, help="Device friendly_name")
@click.pass_context
def cli(ctx, broker, port, device):
    ctx.ensure_object(dict)
    ctx.obj["broker"] = broker
    ctx.obj["port"] = port
    ctx.obj["device"] = device


def require_broker(ctx):
    broker = ctx.obj["broker"]
    if not broker:
        click.echo("Error: --broker / ZIGBEE_BROKER is required", err=True)
        sys.exit(1)
    return broker


def get_ctx_device(ctx):
    """Resolve device name and caps from cache, requiring --device."""
    device = ctx.obj["device"]
    if not device:
        click.echo("Error: --device / ZIGBEE_DEVICE is required", err=True)
        sys.exit(1)
    cache = require_cache()
    return device, get_device_info(cache, device)["caps"]


# ---------------------------------------------------------------------------
# scan
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--list", "list_only", is_flag=True, help="List cached devices without scanning")
@click.pass_context
def scan(ctx, list_only):
    """Scan bridge/devices and cache device capabilities."""
    if list_only:
        cache = require_cache()
        click.echo(f"Cached devices ({CACHE_FILE}):")
        for name, info in cache.items():
            model = info.get("model", "unknown")
            caps = ", ".join(info["caps"].keys())
            click.echo(f"  {name}  [{model}]  {caps}")
        return

    broker, port = require_broker(ctx), ctx.obj["port"]
    click.echo(f"Scanning {broker}:{port} ...")

    raw = mqtt_fetch_once(broker, port, "zigbee2mqtt/bridge/devices")
    if raw is None:
        click.echo("Error: no response from broker", err=True)
        sys.exit(1)

    cache = {}
    for dev in raw:
        if dev.get("type") == "Coordinator":
            continue
        definition = dev.get("definition")
        if not definition:
            continue
        friendly_name = dev["friendly_name"]
        caps = parse_exposes(definition.get("exposes", []))
        cache[friendly_name] = {
            "model": definition.get("model", ""),
            "vendor": definition.get("vendor", ""),
            "description": definition.get("description", ""),
            "caps": caps,
        }

    save_cache(cache)
    click.echo(f"Found {len(cache)} device(s), saved to {CACHE_FILE}:")
    for name, info in cache.items():
        caps = ", ".join(info["caps"].keys())
        click.echo(f"  {name}  [{info['model']}]  {caps}")


# ---------------------------------------------------------------------------
# info
# ---------------------------------------------------------------------------

@cli.command()
@click.pass_context
def info(ctx):
    """Show capabilities of the specified device from cache."""
    device, caps = get_ctx_device(ctx)
    cache = require_cache()
    meta = cache[device]

    click.echo(f"Device:      {device}")
    click.echo(f"Model:       {meta['model']}")
    click.echo(f"Vendor:      {meta['vendor']}")
    click.echo(f"Description: {meta['description']}")
    click.echo("Capabilities:")

    for cap, val in caps.items():
        if cap == "brightness":
            click.echo(f"  brightness     range {val['min']} - {val['max']}")
        elif cap == "color_temp":
            presets = ", ".join(val["presets"]) if val.get("presets") else "none"
            click.echo(f"  color_temp     range {val['min']} - {val['max']} mired  presets: {presets}")
        elif cap == "effect":
            click.echo(f"  effect         {', '.join(val)}")
        elif cap == "color_power_on_behavior":
            click.echo(f"  poweron        {', '.join(val)}")
        elif cap in ("state", "color", "do_not_disturb"):
            click.echo(f"  {cap}")


# ---------------------------------------------------------------------------
# Light commands
# ---------------------------------------------------------------------------

@cli.command()
@click.pass_context
def on(ctx):
    """Turn the light on."""
    device, _ = get_ctx_device(ctx)
    mqtt_send(require_broker(ctx), ctx.obj["port"], device, {"state": "ON"})
    click.echo("ON")


@cli.command()
@click.pass_context
def off(ctx):
    """Turn the light off."""
    device, _ = get_ctx_device(ctx)
    mqtt_send(require_broker(ctx), ctx.obj["port"], device, {"state": "OFF"})
    click.echo("OFF")


@cli.command()
@click.pass_context
def toggle(ctx):
    """Toggle the light."""
    device, _ = get_ctx_device(ctx)
    mqtt_send(require_broker(ctx), ctx.obj["port"], device, {"state": "TOGGLE"})
    click.echo("TOGGLE")


@cli.command()
@click.argument("value")
@click.option("--transition", "-t", default=None, type=float)
@click.pass_context
def brightness(ctx, value, transition):
    """Set brightness. VALUE can be 0-254 or a percentage like 50%."""
    device, caps = get_ctx_device(ctx)
    b = caps.get("brightness", {"min": 0, "max": 254})
    val = parse_percent_or_value(value, b["min"], b["max"])
    payload = {"brightness": val}
    if transition is not None:
        payload["transition"] = transition
    mqtt_send(require_broker(ctx), ctx.obj["port"], device, payload)
    click.echo(f"Brightness: {val} ({value_to_percent(val, b['min'], b['max'])}%)")


@cli.command()
@click.argument("value")
@click.option("--transition", "-t", default=None, type=float)
@click.pass_context
def temp(ctx, value, transition):
    """Set color temperature. VALUE can be mired, preset name, or percentage."""
    device, caps = get_ctx_device(ctx)
    ct = caps.get("color_temp", {"min": 153, "max": 500, "presets": []})
    presets = ct.get("presets", [])

    if value in presets:
        payload = {"color_temp": value}
        display = value
    else:
        val = parse_percent_or_value(value, ct["min"], ct["max"])
        payload = {"color_temp": val}
        display = f"{val} mired ({value_to_percent(val, ct['min'], ct['max'])}%)"

    if transition is not None:
        payload["transition"] = transition
    mqtt_send(require_broker(ctx), ctx.obj["port"], device, payload)
    click.echo(f"Color temp: {display}")


@cli.command()
@click.argument("value")
@click.option("--transition", "-t", default=None, type=float)
@click.pass_context
def color(ctx, value, transition):
    """Set color. VALUE: #hex, R,G,B, or x:X,y:Y."""
    device, caps = get_ctx_device(ctx)
    if not caps.get("color"):
        click.echo("Error: this device does not support color", err=True)
        sys.exit(1)

    if value.startswith("#"):
        color_payload = {"hex": value}
    elif value.startswith("x:"):
        parts = dict(p.split(":") for p in value.split(","))
        color_payload = {"x": float(parts["x"]), "y": float(parts["y"])}
    else:
        color_payload = {"rgb": value}

    payload = {"color": color_payload}
    if transition is not None:
        payload["transition"] = transition
    mqtt_send(require_broker(ctx), ctx.obj["port"], device, payload)
    click.echo(f"Color: {value}")


@cli.command()
@click.argument("name")
@click.pass_context
def effect(ctx, name):
    """Trigger a light effect."""
    device, caps = get_ctx_device(ctx)
    valid = caps.get("effect", [])
    if not valid:
        click.echo("Error: this device does not support effects", err=True)
        sys.exit(1)
    if name not in valid:
        click.echo(f"Error: unknown effect '{name}'. Valid: {', '.join(valid)}", err=True)
        sys.exit(1)
    mqtt_send(require_broker(ctx), ctx.obj["port"], device, {"effect": name})
    click.echo(f"Effect: {name}")


@cli.command()
@click.argument("value")
@click.pass_context
def poweron(ctx, value):
    """Set power-on behavior."""
    device, caps = get_ctx_device(ctx)
    valid = caps.get("color_power_on_behavior", [])
    if not valid:
        click.echo("Error: this device does not support color_power_on_behavior", err=True)
        sys.exit(1)
    if value not in valid:
        click.echo(f"Error: invalid value '{value}'. Valid: {', '.join(valid)}", err=True)
        sys.exit(1)
    mqtt_send(require_broker(ctx), ctx.obj["port"], device, {"color_power_on_behavior": value})
    click.echo(f"Power-on behavior: {value}")


@cli.command()
@click.argument("value", type=click.Choice(["on", "off"]))
@click.pass_context
def dnd(ctx, value):
    """Set do-not-disturb mode."""
    device, caps = get_ctx_device(ctx)
    if not caps.get("do_not_disturb"):
        click.echo("Error: this device does not support do_not_disturb", err=True)
        sys.exit(1)
    mqtt_send(require_broker(ctx), ctx.obj["port"], device, {"do_not_disturb": value == "on"})
    click.echo(f"Do-not-disturb: {value}")


@cli.command("set")
@click.option("--state", type=click.Choice(["on", "off", "toggle"]), default=None)
@click.option("--brightness", "-b", "brightness_val", default=None)
@click.option("--temp", "-t", "temp_val", default=None)
@click.option("--color", "color_val", default=None)
@click.option("--transition", default=None, type=float)
@click.option("--on-time", default=None, type=int)
@click.pass_context
def set_cmd(ctx, state, brightness_val, temp_val, color_val, transition, on_time):
    """Set multiple properties at once."""
    device, caps = get_ctx_device(ctx)
    b = caps.get("brightness", {"min": 0, "max": 254})
    ct = caps.get("color_temp", {"min": 153, "max": 500, "presets": []})

    payload = {}
    summary = []

    if state:
        payload["state"] = state.upper()
        summary.append(f"state={state.upper()}")

    if brightness_val:
        val = parse_percent_or_value(brightness_val, b["min"], b["max"])
        payload["brightness"] = val
        summary.append(f"brightness={val}({value_to_percent(val, b['min'], b['max'])}%)")

    if temp_val:
        presets = ct.get("presets", [])
        if temp_val in presets:
            payload["color_temp"] = temp_val
            summary.append(f"color_temp={temp_val}")
        else:
            val = parse_percent_or_value(temp_val, ct["min"], ct["max"])
            payload["color_temp"] = val
            summary.append(f"color_temp={val}")

    if color_val:
        if not caps.get("color"):
            click.echo("Error: this device does not support color", err=True)
            sys.exit(1)
        if color_val.startswith("#"):
            payload["color"] = {"hex": color_val}
        elif color_val.startswith("x:"):
            parts = dict(p.split(":") for p in color_val.split(","))
            payload["color"] = {"x": float(parts["x"]), "y": float(parts["y"])}
        else:
            payload["color"] = {"rgb": color_val}
        summary.append(f"color={color_val}")

    if transition is not None:
        payload["transition"] = transition
        summary.append(f"transition={transition}s")

    if on_time is not None:
        payload["on_time"] = on_time
        summary.append(f"on_time={on_time}s")

    if not payload:
        click.echo("Nothing to set.", err=True)
        sys.exit(1)

    mqtt_send(require_broker(ctx), ctx.obj["port"], device, payload)
    click.echo("Set: " + ", ".join(summary))


@cli.command("get")
@click.argument("fields", nargs=-1)
@click.pass_context
def get_cmd(ctx, fields):
    """Get current state. Optionally specify fields: state brightness color_temp color."""
    device, caps = get_ctx_device(ctx)
    state = mqtt_get_state(require_broker(ctx), ctx.obj["port"], device)
    if not state:
        click.echo("No response from device (timeout).", err=True)
        sys.exit(1)
    click.echo(format_state(state, caps, list(fields) if fields else None))


if __name__ == "__main__":
    cli()
