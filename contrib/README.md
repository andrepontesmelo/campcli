# systemd user unit for `campcli daemon`

Long-running poller that sends Telegram notifications when new campsites
appear. Runs as a per-user systemd unit (no root needed).

## Setup

1. Create a Telegram bot with [@BotFather](https://t.me/BotFather), grab the
   token. Send the bot a message, then fetch your `chat_id` from
   `https://api.telegram.org/bot<TOKEN>/getUpdates`.

2. Create the env file (chmod 600):

   ```sh
   mkdir -p ~/.config/campcli
   cat > ~/.config/campcli/telegram.env <<EOF
   TELEGRAM_BOT_TOKEN=...
   TELEGRAM_CHAT_ID=...
   EOF
   chmod 600 ~/.config/campcli/telegram.env
   ```

3. Install the unit:

   ```sh
   mkdir -p ~/.config/systemd/user
   cp contrib/campcli-daemon.service ~/.config/systemd/user/
   loginctl enable-linger $USER          # survive logout
   systemctl --user daemon-reload
   systemctl --user enable --now campcli-daemon
   journalctl --user -u campcli-daemon -f
   ```

The unit assumes `campcli` is on `~/.local/bin/campcli`. If you installed
with `uv tool install` or similar, adjust `ExecStart=` to match
`which campcli`.
