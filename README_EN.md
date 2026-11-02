# Discord Bot with Built-in AI
[RU](./README.md) | EN

## Questions

### What is this?
Well, if it wasn't clear from the name, this is a Discord bot with an integrated AI assistant.
> btw, the bot is written in Python.

### What is this bot made for?
The bot is currently being written for a small Minecraft Discord server so players can chat with it, idrk.  
By design, it's meant to be a bot you can: chat with, ask questions about the server, ask for help with Minecraft, etc.

### Why openrouter?
Because it's free ¯\\\_(ツ)\_/¯

## Limitations
The only limitations are that it cannot write code and its responses cannot exceed 2000 characters.

## How to install it?

### Part 1 (In Browser)
1. Open the [Discord Developer Portal](https://discord.com/developers/home) and create a new bot.
2. Under the "Bot" tab, generate a token and save it for later.
3. In the same tab, enable **Presence Intent**, **Server Members Intent**, and **Message Content Intent**.
4. Open [OpenRouter API key](https://openrouter.ai/workspaces/default/keys), create an API key, and copy it.

### Part 2 (On Server)
Install all necessary packages.

On Debian/Ubuntu:
```bash
apt update && apt install git python3 python3-pip -y
```

Clone the repository and install all required libraries:
```bash
git clone https://github.com/timurtom/DiscordAIBot.git
cd DiscordAIBot
pip install discord.py openai python-dotenv
```

Rename `example.env` to `.env` and insert your API keys also rename `system_prompt_example.txt` to `system_prompt.txt`
```
mv example.env .env
mv system_prompt_example.txt system_prompt_example.txt
```
Start the bot
```
python bot.py
```
## To-Do List

- [x] Write the bot itself
- [x] Move limitations to a separate file
- [x] Make it answer frequently asked questions about the server
