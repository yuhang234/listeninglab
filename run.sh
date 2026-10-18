#!/bin/bash
# ListeningLab launcher
PORT=8765
if [[ "$1" == "--port" && -n "$2" ]]; then
  PORT="$2"
fi
python3 app/server.py --port "$PORT"