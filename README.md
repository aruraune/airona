# Airona-chan

A Discord bot that reminds you about raids.

## 🛠️ Self-hosting

Requires [uv](https://docs.astral.sh/uv/).

1. Clone this repository.
    ```sh
    git clone https://github.com/aruraune/airona
    cd airona
    ```
1. Create `env/discord.toml` with your Discord bot token:
    ```toml
    token = ""
    ```
1. Create `env/config.toml`:
    ```toml
    [db]
    url = "sqlite:///save/airona.db"

    [apscheduler]
    jobstore = "sqlite:///save/jobstore.db"

    [sqlalchemy]
    log_level = 30 # WARNING
    ```
1. Create `env/raid.toml`:
   ```toml
   raid_cleanup_interval = 30
   
   raid_message_template = """
   {title}
   Apply on {host_mention} {host_username} #{host_uid} <t:{when}:R> @ <t:{when}:F>
   
   {dps_emoji} {dps_users}
   
   {tank_emoji} {tank_users}
   
   {support_emoji} {support_users}
   
   Interested users are shown in the order they expressed interest.
   The Leader may choose players at their own discretion.
   PRESS YOUR ROLE BELOW TO SHOW YOUR INTEREST.
   Press {has_cleared_emoji} if you have already cleared.
   
   View {raid_message_link} to use the buttons."""
   
   raid_ping_template = """
   {title} by {host_mention} {host_username} #{host_uid}: {raid_message_link}
   Pings: {users}
   """
   
   raid_removal_dm_template = """
   You were removed from the raid {title} scheduled for <t:{when}:F>.
   Reason: {raid_removal_reason}
   """
   
   [emoji]
   dps = "<:bpsr_dps:1449010393916903586>"
   tank = "<:bpsr_tank:1449010397754691667>"
   support = "<:bpsr_support:1449010395997274133>"
   has_cleared = "👍"
   sign_off = "❌"
   ```
    View [env.py](src/airona/env.py) for the full configuration schema.
1. Initialize the database:
    ```sh
    mkdir save
    uv run airona-init-db
    ```
1. Run with `uv run airona`.
