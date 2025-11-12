# Feste-chan

A Discord bot that reminds you to do periodic tasks.

# Official Instance

[Add Feste-chan to a server!](https://discord.com/oauth2/authorize?client_id=1436467404401283121)

# 🛠️ Self-hosting

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
    View [env.py](src/feste/env.py) for the full configuration schema.
1. Initialize the database:
    ```sh
    mkdir save
    uv run feste-init-db
    ```
1. Run with `uv run feste`.
