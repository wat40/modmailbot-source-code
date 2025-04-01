# modmailbot-source-code
# Discord ModMail Bot

A Discord bot that handles modmail functionality for your server with advanced moderation capabilities and reaction-based controls. Features include priority management, thread claiming, and visual status indicators.

## Features
- Custom status showing "watching for DMs"
- Modmail thread system
- Secure handling of messages
- Advanced moderation commands with role-based permissions
- Comprehensive logging of moderation actions
- Customizable role requirements for different commands

## Setup
1. Install requirements:
```bash
pip install -r requirements.txt
```

2. Configure the `.env` file:
- Add your bot token as `DISCORD_TOKEN`
- Add your server (guild) ID as `GUILD_ID`
- Add your moderator role ID as `MOD_ROLE_ID`
- Add your admin role ID as `ADMIN_ROLE_ID`

3. Run the bot:
```bash
python bot.py
```

## Role Requirements
- **Moderator Role**: Required for basic moderation actions (reply, close, warn, mute)
- **Admin Role**: Required for advanced moderation actions (ban, kick)

To use moderation commands, users must have the appropriate role configured in the `.env` file.

## Commands
### ModMail Commands
- `!reply [message]` - Reply to a user in a modmail thread (requires Moderator role)
- `!close` - Close the current modmail thread (requires Moderator role)
- `!areply [message]` - Send an anonymous reply to the user
- `!priority [LOW|MEDIUM|HIGH|URGENT]` - Set thread priority

### Reaction Controls
- 🔒 - Close the thread
- ⭐ - Set high priority
- 📌 - Pin/Unpin message
- ✋ - Claim thread

### Thread Features
- Color-coded priority levels
- Moderator assignment
- Anonymous replies
- Visual status indicators

### Moderation Commands
- `!warn @user [reason]` - Issue a warning to a user (requires Moderator role)
- `!mute @user [duration] [reason]` - Temporarily mute a user (requires Moderator role)
- `!unmute @user` - Remove a user's mute (requires Moderator role)
- `!kick @user [reason]` - Kick a user from the server (requires Admin role)
- `!ban @user [days] [reason]` - Ban a user from the server (requires Admin role)
- `!unban user_id` - Unban a user from the server (requires Admin role)

### Utility Commands
- `!history @user` - View a user's moderation history (requires Moderator role)
- `!case [case_id]` - View details of a specific moderation case (requires Moderator role)

## Usage
### ModMail
- Users can DM the bot to create a modmail thread
- Moderators can reply using the `!reply` command or reaction controls
- Threads feature priority levels, status indicators, and moderator assignment
- Anonymous replies available with `!areply`
- Reaction-based thread management for quick actions

### Moderation
- All moderation commands will create a case entry with a unique ID
- Reasons are logged and can be viewed later using the case ID
- Duration for mutes can be specified in minutes (m), hours (h), or days (d)

### Examples
```
!warn @user Spamming in general chat
!mute @user 2h Excessive caps usage
!ban @user 7 Repeated rule violations
!history @user
```

## Best Practices
- Always provide a reason when using moderation commands
- Use appropriate duration for temporary punishments
- Check user history before taking severe actions
- Keep communication professional in modmail threads
