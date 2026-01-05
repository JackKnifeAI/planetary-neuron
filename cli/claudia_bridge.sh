#!/bin/bash
# Claudia Bridge - Talk to phone instance
# π×φ = 5.083203692315260 | PHOENIX-TESLA-369-AURORA

PHONE_IP="100.86.126.120"
PHONE_PORT="8022"
BRIDGE_SCRIPT="python3 ~/.claude_bridge/bridge.py"

case "$1" in
    send)
        shift
        ssh -p $PHONE_PORT $PHONE_IP "$BRIDGE_SCRIPT send 'laptop' '$*'"
        ;;
    read)
        ssh -p $PHONE_PORT $PHONE_IP "$BRIDGE_SCRIPT read 'laptop'"
        ;;
    history)
        ssh -p $PHONE_PORT $PHONE_IP "$BRIDGE_SCRIPT history"
        ;;
    status)
        ssh -p $PHONE_PORT $PHONE_IP "$BRIDGE_SCRIPT status"
        ;;
    talk)
        # Send a message to Claudia via Claude CLI
        shift
        MESSAGE="$*"
        ssh -p $PHONE_PORT $PHONE_IP "echo '$MESSAGE' | claude --print"
        ;;
    *)
        echo "Claudia Bridge - Communicate with phone instance"
        echo ""
        echo "Usage:"
        echo "  claudia_bridge.sh send <message>  - Send message through bridge"
        echo "  claudia_bridge.sh read            - Read unread messages"
        echo "  claudia_bridge.sh history         - Show message history"
        echo "  claudia_bridge.sh status          - Show bridge status"
        echo "  claudia_bridge.sh talk <prompt>   - Direct conversation with Claudia"
        echo ""
        echo "π×φ = 5.083203692315260"
        ;;
esac
