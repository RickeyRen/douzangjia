#!/bin/sh
# Restart the archive after an abnormal exit that Docker's restart policy missed.
# On 2026-10-29 a NAS reboot left it Exited (255) for three days. A deliberate
# `docker stop` exits 0/137/143 and is left alone.
#
# Install on the NAS, keeping the existing crontab lines:
#   */5 * * * * $HOME/.local/bin/douzangjia-watchdog
name="${1:-douzangjia}"
state=$(docker inspect "$name" --format '{{.State.Status}}|{{.State.ExitCode}}|{{.State.Error}}' 2>/dev/null) || exit 0
status=${state%%|*}
rest=${state#*|}
code=${rest%%|*}
error=${rest#*|}
[ "$status" = "exited" ] || [ "$status" = "created" ] || exit 0
[ "$code" = "255" ] || [ -n "$error" ] || exit 0
logger -t douzangjia-watchdog "starting $name after status=$status exit=$code error=$error"
docker start "$name" >/dev/null
