#!/bin/sh
# Tail the campcli daemon log (see contrib/campcli-daemon.service).
exec tail -f "${XDG_STATE_HOME:-$HOME/.local/state}/campcli/daemon.log"
