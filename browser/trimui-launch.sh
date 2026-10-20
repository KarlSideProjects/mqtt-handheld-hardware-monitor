#!/bin/sh
set -eu
base=/mnt/UDISK/hwmonitor
cd "$base/app"
bash ./trimui-awake.sh
export MQTT_CONFIG="$base/mqtt-config.json"
export PYTHONPATH="$base/runtime/python${PYTHONPATH:+:$PYTHONPATH}"
export LD_LIBRARY_PATH="$base/runtime/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export PATH="$base/runtime/bin:$PATH"
export TRIMUI_BROWSER="$base/runtime/bin/chromium"
exec python3 trimui_monitor.py >>"$base/launch.log" 2>&1
