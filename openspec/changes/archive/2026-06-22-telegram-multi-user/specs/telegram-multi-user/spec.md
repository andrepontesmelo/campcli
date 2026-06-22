# telegram-multi-user Specification

## Purpose
Multi-user Telegram bot: authorized-ID gate, per-user verbose toggle with inline keyboard, broadcast alerts, command auto-complete. Extends profile.json with `tg_allowed_ids`.

## ADDED Requirements

### Requirement: Profile includes authorized Telegram IDs
The Profile model SHALL include a `tg_allowed_ids` field of type `list[int]`, defaulting to an empty list.
`profile.json` SHALL include `"tg_allowed_ids"` in its JSON schema.
When `tg_allowed_ids` is empty, the daemon SHALL send no alerts and respond to no commands.

#### Scenario: Default profile has empty list
- **WHEN** profile.json is generated as default
- **THEN** it contains `"tg_allowed_ids": []`

#### Scenario: Profile with authorized IDs
- **WHEN** profile.json has `"tg_allowed_ids": [12345, 67890]`
- **THEN** the daemon loads and uses these IDs for auth and broadcast

#### Scenario: Existing profile.json without field loads with default
- **WHEN** an existing profile.json lacks the `tg_allowed_ids` key
- **THEN** Pydantic uses the default value `[]` and the profile loads successfully

### Requirement: Daemon requires only TELEGRAM_BOT_TOKEN
The daemon SHALL require only the `TELEGRAM_BOT_TOKEN` environment variable to start.
`TELEGRAM_CHAT_ID` SHALL no longer be read or required.
The daemon SHALL exit with code 2 if `TELEGRAM_BOT_TOKEN` is not set.

#### Scenario: Daemon starts without TELEGRAM_CHAT_ID
- **WHEN** `TELEGRAM_BOT_TOKEN` is set and `TELEGRAM_CHAT_ID` is not
- **THEN** the daemon starts and broadcasts to users from `tg_allowed_ids`

#### Scenario: Daemon fails without token
- **WHEN** `TELEGRAM_BOT_TOKEN` is not set
- **THEN** the daemon exits with code 2 and an error message

### Requirement: Authorized-users gate
The bot SHALL only process commands from Telegram user IDs listed in `tg_allowed_ids`.
When an unauthorized user sends a message, the bot SHALL reply with a message containing the sender's Telegram ID and instructions to contact an admin.
When `tg_allowed_ids` is empty, the bot SHALL reply to every message with the ID-revealing message.

#### Scenario: Authorized user sends /verbose
- **WHEN** user 12345 (in tg_allowed_ids) sends `/verbose`
- **THEN** the bot processes the command

#### Scenario: Unauthorized user sends any message
- **WHEN** user 99999 (not in tg_allowed_ids) sends any text
- **THEN** the bot replies "Your Telegram ID is 99999. Ask an admin to run: campcli telegram allow 99999"

### Requirement: Broadcast alerts to all authorized users
When `SearchNotifier` clears a WeekendMatch for notification, the bot SHALL send the rendered match message to every authorized user's last-seen chat.
Users who have never interacted with the bot (no `chat:{tg_id}` setting) SHALL be skipped for alert delivery.
Dedup and suppression SHALL run once per poll cycle, not per user.

#### Scenario: Two authorized users, both known chats
- **WHEN** users 12345 (chat abc) and 67890 (chat xyz) are authorized, and a WeekendMatch is found
- **THEN** the match message is sent to both chat abc and chat xyz

#### Scenario: Authorized user never interacted
- **WHEN** user 12345 is authorized but has no `chat:{tg_id}` setting
- **THEN** alerts are not sent to that user (no known destination)

### Requirement: Per-user verbose mode
Each authorized user SHALL have an independent verbose toggle, persisted in Settings DB under key `verbose:{tg_id}` with value `"on"` or `"off"`.
When per-user verbose is ON, all daemon log lines SHALL be sent to that user's last-seen chat.
When per-user verbose is OFF, only alerts (not log lines) SHALL be sent to that user.
Per-user verbose SHALL be toggled via the `/verbose` command or its inline keyboard reply.
The global `verbose` settings key SHALL be dropped.

#### Scenario: User toggles verbose ON
- **WHEN** user 12345 sends `/verbose` and presses the [ON] button
- **THEN** `verbose:12345` is set to `"on"` and subsequent log lines are sent to user 12345's chat

#### Scenario: User toggles verbose OFF
- **WHEN** user 12345 (with verbose ON) presses the [OFF] button
- **THEN** `verbose:12345` is set to `"off"` and log lines stop going to user 12345's chat

#### Scenario: Two users, one verbose ON, one OFF
- **WHEN** user 12345 has verbose ON and user 67890 has verbose OFF
- **THEN** daemon log lines go to user 12345's chat only; alerts go to both

### Requirement: /verbose command with inline keyboard
The `/verbose` command SHALL reply with a message containing the current verbose state and two inline buttons: `[ON]` and `[OFF]`.
Pressing a button SHALL send a callback query that the bot handles to toggle the user's verbose state.
The bot SHALL edit the reply message to confirm the new state after the toggle.
The bot SHALL call `answer_callback_query` to acknowledge the button press.

#### Scenario: User sends /verbose
- **WHEN** user 12345 sends `/verbose`
- **THEN** the bot replies with a message like "verbose logging for your account: OFF" and shows `[ON] [OFF]` inline buttons

#### Scenario: User presses ON button
- **WHEN** user 12345 (currently verbose OFF) presses the [ON] button
- **THEN** verbose is toggled ON, the message is edited to "verbose logging for your account: ON", and the callback query is answered

### Requirement: Bot registers commands with Telegram
On daemon startup, the bot SHALL call the Telegram Bot API `setMyCommands` method to register `/verbose` (and future commands) so they appear with auto-complete in the chat input.
The command list SHALL be derived from the command router's registered commands.

#### Scenario: Daemon starts
- **WHEN** the daemon starts
- **THEN** `setMyCommands` is called with `[{"command": "verbose", "description": "Toggle verbose daemon logging"}]`

### Requirement: Last-seen chat tracking
For each authorized user, the bot SHALL store the chat_id of their most recent interaction in Settings DB key `chat:{tg_id}`.
This mapping SHALL update on every incoming command or callback query from that user.
The last-seen chat SHALL be used as the alert and verbose-log destination for that user.

#### Scenario: User messages from a new chat
- **WHEN** user 12345 (previously chat abc) sends a message from chat xyz
- **THEN** `chat:12345` is updated to `xyz`

### Requirement: CLI telegram subcommand
The CLI SHALL provide a `telegram` subcommand group with three commands:
- `allow <tg_id> [<tg_id> ...]` — add one or more IDs to `tg_allowed_ids` in profile.json
- `revoke <tg_id> [<tg_id> ...]` — remove one or more IDs from `tg_allowed_ids` in profile.json
- `list` — display current `tg_allowed_ids` from profile.json

The `allow` command SHALL prevent duplicates (no-op if ID already present).
The `revoke` command SHALL report "not found" for IDs not in the list.
All commands SHALL exit with code 2 if profile.json does not exist.

#### Scenario: Add a new authorized user
- **WHEN** user runs `campcli telegram allow 12345`
- **THEN** 12345 is added to `tg_allowed_ids` in profile.json and confirmed in output

#### Scenario: Revoke an authorized user
- **WHEN** user runs `campcli telegram revoke 12345`
- **THEN** 12345 is removed from profile.json and confirmed in output

#### Scenario: List authorized users
- **WHEN** user runs `campcli telegram list`
- **THEN** current tg_allowed_ids are displayed, or "no authorized telegram users" if empty




