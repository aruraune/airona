# Feste-chan

A Discord bot that reminds you to do periodic tasks.

## Official Instance

[Add Feste-chan to a server!](https://discord.com/oauth2/authorize?client_id=1436467404401283121)

## 🛠️ Self-hosting

Requires [uv](https://docs.astral.sh/uv/).

1. Clone this repository.
    ```sh
    git clone https://github.com/kuwifuwa/feste
    cd feste
    ```
1. Create `env/discord.toml` with your Discord bot token:
    ```toml
    token = ""
    ```
1. Create `env/config.toml`:
    ```toml
    glue_interval = 30
    subscribers_interval = 1800

    [db]
    url = "sqlite:///save/feste.db"

    [apscheduler]
    jobstore = "sqlite:///save/jobstore.db"

    [sqlalchemy]
    log_level = 30 # WARNING
    ```
1. Create `env/raid.toml`:
   ```toml
   raid_cleanup_interval = 30
   
   template = """
   {title}
   Apply on {host_mention} <t:{when}:R> @ <t:{when}:F>
   
   {dps_emoji} {dps_users}
   
   {tank_emoji} {tank_users}
   
   {support_emoji} {support_users}
   
   Interested users are shown in the order they expressed interest.
   The Leader may choose players at their own discretion.
   PRESS YOUR ROLE BELOW TO SHOW YOUR INTEREST.
   Press {has_cleared_emoji} if you have already cleared."""
   
   [emoji]
   dps = "<:bpsr_dps:1449010393916903586>"
   tank = "<:bpsr_tank:1449010397754691667>"
   support = "<:bpsr_support:1449010395997274133>"
   has_cleared = "👍"
   sign_off = "❌"
   ```
    View [env.py](src/feste/env.py) for the full configuration schema.
1. Initialize the database:
    ```sh
    mkdir save
    uv run feste-init-db
    ```
1. Run with `uv run feste`.
