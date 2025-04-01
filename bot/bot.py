import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import asyncio
import aiohttp
from database import Database
from utils import parse_duration, has_mod_role, has_admin_role, format_duration
from datetime import datetime

# Load environment variables
load_dotenv()

# Configure logging
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Bot configuration
intents = discord.Intents.all()

class CustomBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=self.get_prefix, intents=intents)
        self.initial_retry_delay = 1
        self.max_retry_delay = 60
        self.max_retries = 5

    async def get_prefix(self, message):
        return '-'

    async def setup_hook(self):
        # Initialize status update task
        self.loop.create_task(self.update_status())

    async def update_status(self):
        try:
            while True:
                # Update bot status with current info
                guild_count = len(self.guilds)
                thread_count = len(active_threads)
                status = f"📊 {guild_count} Servers | 📬 {thread_count} Threads | -help"
                activity = discord.Activity(
                    type=discord.ActivityType.watching,
                    name=status
                )
                await self.change_presence(activity=activity)
                await asyncio.sleep(60)
        except Exception as e:
            logging.error(f"Error in status update: {e}")

    async def start(self, token, *, reconnect=True):
        retry_count = 0
        current_delay = self.initial_retry_delay

        while retry_count < self.max_retries:
            try:
                await super().start(token, reconnect=reconnect)
                return
            except aiohttp.client_exceptions.ClientConnectorDNSError as e:
                retry_count += 1
                if retry_count >= self.max_retries:
                    logging.error(f"Failed to connect after {self.max_retries} attempts: {e}")
                    raise
                
                logging.warning(f"Connection attempt {retry_count} failed. Retrying in {current_delay} seconds...")
                await asyncio.sleep(current_delay)
                current_delay = min(current_delay * 2, self.max_retry_delay)
            except Exception as e:
                logging.error(f"Unexpected error during connection: {e}")
                raise

bot = CustomBot()

# Initialize database
db = Database()

# Initialize active threads dictionary
active_threads = {}

# Help command is now handled by the help group command defined below

@bot.event
async def on_guild_join(guild):
    # Initialize guild settings
    db.get_guild_settings(guild.id)

@bot.event
async def on_member_join(member):
    settings = db.get_guild_settings(member.guild.id)
    
    # Auto-role assignment
    if settings['auto_role_id']:
        try:
            role = member.guild.get_role(settings['auto_role_id'])
            if role:
                await member.add_roles(role)
        except discord.HTTPException:
            pass
    
    # Welcome message
    if settings['welcome_channel_id'] and settings['welcome_message']:
        channel = member.guild.get_channel(settings['welcome_channel_id'])
        if channel:
            welcome_msg = settings['welcome_message'].replace('{user}', member.mention)
            welcome_msg = welcome_msg.replace('{server}', member.guild.name)
            try:
                await channel.send(welcome_msg)
            except discord.HTTPException:
                pass

@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id:
        return

    channel = bot.get_channel(payload.channel_id)
    if not channel or channel.id not in active_threads:
        return

    message = await channel.fetch_message(payload.message_id)
    user = bot.get_user(payload.user_id)
    thread = active_threads[channel.id]

    # Check if user has mod role or is owner
    guild = channel.guild
    member = await guild.fetch_member(payload.user_id)
    if not (has_mod_role(member) or is_owner(member.id)):
        return

    emoji = str(payload.emoji)
    
    if emoji == '🔒':  # Close thread
        await message.remove_reaction(emoji, user)
        await channel.send(f"Thread closed by {user.mention}")
        await _close_handler(channel, user)
    elif emoji == '⭐':  # High priority
        await message.remove_reaction(emoji, user)
        thread.priority = ThreadPriority.HIGH
        embed = create_thread_embed(thread, bot.get_user(thread.user_id))
        await message.edit(embed=embed)
    elif emoji == '📌':  # Pin/Unpin message
        await message.remove_reaction(emoji, user)
        try:
            if message.pinned:
                await message.unpin()
                await channel.send(f"Message unpinned by {user.mention}")
            else:
                await message.pin()
                await channel.send(f"Message pinned by {user.mention}")
        except discord.HTTPException:
            await channel.send("❌ Failed to pin/unpin message")
    elif emoji == '✋':  # Claim thread
        await message.remove_reaction(emoji, user)
        thread.assigned_mod = f"{user.name}#{user.discriminator}"
        embed = create_thread_embed(thread, bot.get_user(thread.user_id))
        await message.edit(embed=embed)
        await channel.send(f"Thread claimed by {user.mention}")

    async def update_status(self):
        while True:
            try:
                active_thread_count = len(active_threads)
                guild_count = len(self.guilds)
                status_message = f"📬 {guild_count} servers | {active_thread_count} active threads | -help"
                await self.change_presence(
                    activity=discord.Activity(
                        type=discord.ActivityType.WATCHING,
                        name=status_message
                    ),
                    status=discord.Status.online
                )
            except Exception as e:
                logging.error(f"Failed to update status: {e}")
            await asyncio.sleep(300)  # Update every 5 minutes

# Reply command is implemented below to avoid duplication

async def _reply_handler(ctx_or_interaction, message: str, anonymous: bool = False):
    is_interaction = isinstance(ctx_or_interaction, discord.Interaction)
    channel = ctx_or_interaction.channel
    author = ctx_or_interaction.user if is_interaction else ctx_or_interaction.author

    if not channel.id in active_threads:
        response = "❌ This command can only be used in ModMail threads!"
        if is_interaction:
            await ctx_or_interaction.response.send_message(response, ephemeral=True)
        else:
            await ctx_or_interaction.send(response)
        return

    thread = active_threads[channel.id]
    user = bot.get_user(thread.user_id)
    if not user:
        response = "❌ Could not find the user associated with this thread!"
        if is_interaction:
            await ctx_or_interaction.response.send_message(response, ephemeral=True)
        else:
            await ctx_or_interaction.send(response)
        return

    # Send reply to user
    embed = discord.Embed(
        description=message,
        color=discord.Color.blue(),
        timestamp=datetime.now()
    )
    author_name = "Staff" if anonymous else f"{author.name}#{author.discriminator}"
    embed.set_author(name=author_name)
    await user.send(embed=embed)

    # Log reply in thread
    thread.add_log_entry(str(author), message, is_anonymous=anonymous)
    
    if is_interaction:
        await ctx_or_interaction.response.send_message("✅ Reply sent!", ephemeral=True)
    else:
        await ctx_or_interaction.message.add_reaction('✅')

@bot.command(name='areply')
@commands.check(has_mod_role)
async def anonymous_reply(ctx, *, message: str):
    await _reply_handler(ctx, message, True)

@bot.command(name='priority')
@commands.check(has_mod_role)
async def set_priority(ctx, priority: str):
    await _priority_handler(ctx, priority)

async def _priority_handler(ctx_or_interaction, priority: str):
    is_interaction = isinstance(ctx_or_interaction, discord.Interaction)
    channel = ctx_or_interaction.channel

    if not channel.id in active_threads:
        response = "❌ This command can only be used in ModMail threads!"
        if is_interaction:
            await ctx_or_interaction.response.send_message(response, ephemeral=True)
        else:
            await ctx_or_interaction.send(response)
        return

    try:
        priority_enum = ThreadPriority[priority.upper()]
        thread = active_threads[channel.id]
        thread.priority = priority_enum
        embed = create_thread_embed(thread, bot.get_user(thread.user_id))
        response = f"✅ Thread priority set to {priority.upper()}"
        if is_interaction:
            await ctx_or_interaction.response.send_message(response, embed=embed)
        else:
            await ctx_or_interaction.send(response, embed=embed)
    except KeyError:
        response = "❌ Invalid priority! Use: low, medium, high, or urgent"
        if is_interaction:
            await ctx_or_interaction.response.send_message(response, ephemeral=True)
        else:
            await ctx_or_interaction.send(response)

@bot.command(name='category')
@commands.check(has_mod_role)
async def set_category(ctx, category: str):
    await _category_handler(ctx, category)



async def _category_handler(ctx_or_interaction, category: str):
    is_interaction = isinstance(ctx_or_interaction, discord.Interaction)
    channel = ctx_or_interaction.channel

    if not channel.id in active_threads:
        response = "❌ This command can only be used in ModMail threads!"
        if is_interaction:
            await ctx_or_interaction.response.send_message(response, ephemeral=True)
        else:
            await ctx_or_interaction.send(response)
        return

    try:
        category_enum = ThreadCategory[category.upper()]
        thread = active_threads[channel.id]
        thread.category = category_enum
        embed = create_thread_embed(thread, bot.get_user(thread.user_id))
        response = f"✅ Thread category set to {category.upper()}"
        if is_interaction:
            await ctx_or_interaction.response.send_message(response, embed=embed)
        else:
            await ctx_or_interaction.send(response, embed=embed)
    except KeyError:
        response = "❌ Invalid category! Use: general, support, report, or appeal"
        if is_interaction:
            await ctx_or_interaction.response.send_message(response, ephemeral=True)
        else:
            await ctx_or_interaction.send(response)

@bot.command(name='assign')
@commands.check(has_mod_role)
async def assign_thread(ctx, mod: discord.Member):
    await _assign_handler(ctx, mod)



async def _assign_handler(ctx_or_interaction, mod: discord.Member):
    is_interaction = isinstance(ctx_or_interaction, discord.Interaction)
    channel = ctx_or_interaction.channel

    if not channel.id in active_threads:
        response = "❌ This command can only be used in ModMail threads!"
        if is_interaction:
            await ctx_or_interaction.response.send_message(response, ephemeral=True)
        else:
            await ctx_or_interaction.send(response)
        return

    if not has_mod_role(mod):
        response = "❌ Can only assign threads to moderators!"
        if is_interaction:
            await ctx_or_interaction.response.send_message(response, ephemeral=True)
        else:
            await ctx_or_interaction.send(response)
        return

    thread = active_threads[channel.id]
    thread.assigned_mod = f"{mod.name}#{mod.discriminator}"
    embed = create_thread_embed(thread, bot.get_user(thread.user_id))
    response = f"✅ Thread assigned to {mod.mention}"
    if is_interaction:
        await ctx_or_interaction.response.send_message(response, embed=embed)
    else:
        await ctx_or_interaction.send(response, embed=embed)

@bot.group(name='snippet')
@commands.check(has_mod_role)
async def snippet(ctx):
    if ctx.invoked_subcommand is None:
        await ctx.send_help(ctx.command)

@snippet.command(name='add')
async def add_snippet(ctx, name: str, *, content: str):
    if snippet_manager.add_snippet(ctx.guild.id, name, content):
        await ctx.send(f"✅ Added snippet: `{name}`")
    else:
        await ctx.send("❌ Snippet already exists!")

@snippet.command(name='use')
async def use_snippet(ctx, name: str):
    content = snippet_manager.get_snippet(ctx.guild.id, name)
    if content:
        await reply(ctx, message=content)
    else:
        await ctx.send("❌ Snippet not found!")

@snippet.command(name='remove')
async def remove_snippet(ctx, name: str):
    if snippet_manager.remove_snippet(ctx.guild.id, name):
        await ctx.send(f"✅ Removed snippet: `{name}`")
    else:
        await ctx.send("❌ Snippet not found!")

@snippet.command(name='list')
async def list_snippets(ctx):
    snippets = snippet_manager.list_snippets(ctx.guild.id)
    if snippets:
        await ctx.send("📝 Available snippets:\n" + "\n".join(f"- {s}" for s in snippets))
    else:
        await ctx.send("No snippets available!")

@bot.group(name='config')
@commands.check(has_admin_role)
async def config(ctx):
    if ctx.invoked_subcommand is None:
        settings = db.get_guild_settings(ctx.guild.id)
        embed = discord.Embed(
            title='Server Configuration',
            description='Current server settings:',
            color=discord.Color.blue()
        )
        embed.add_field(name='Prefix', value=settings['prefix'])
        embed.add_field(name='ModMail Category', value=settings['modmail_category'])
        
        welcome_channel = ctx.guild.get_channel(settings['welcome_channel_id']) if settings['welcome_channel_id'] else None
        embed.add_field(name='Welcome Channel', value=welcome_channel.mention if welcome_channel else 'Not set')
        
        auto_role = ctx.guild.get_role(settings['auto_role_id']) if settings['auto_role_id'] else None
        embed.add_field(name='Auto Role', value=auto_role.mention if auto_role else 'Not set')
        
        await ctx.send(embed=embed)

@config.command(name='prefix')
async def set_prefix(ctx, new_prefix: str):
    if len(new_prefix) > 5:
        await ctx.send('❌ Prefix must be 5 characters or less!')
        return
    
    db.update_guild_setting(ctx.guild.id, 'prefix', new_prefix)
    await ctx.send(f'✅ Prefix updated to: `{new_prefix}`')

@config.command(name='welcome')
async def set_welcome(ctx, channel: discord.TextChannel, *, message: str):
    db.update_guild_setting(ctx.guild.id, 'welcome_channel_id', channel.id)
    db.update_guild_setting(ctx.guild.id, 'welcome_message', message)
    await ctx.send(f'✅ Welcome message set in {channel.mention}\nMessage: {message}')

@config.command(name='autorole')
async def set_autorole(ctx, role: discord.Role):
    if role >= ctx.guild.me.top_role:
        await ctx.send('❌ I cannot assign roles higher than my highest role!')
        return
    
    db.update_guild_setting(ctx.guild.id, 'auto_role_id', role.id)
    await ctx.send(f'✅ Auto-role set to: {role.mention}')

@bot.group(name='custom')
@commands.check(lambda ctx: has_admin_role(ctx))
async def custom(ctx):
    if ctx.invoked_subcommand is None:
        commands_list = db.get_custom_commands(ctx.guild.id)
        if not commands_list:
            await ctx.send('No custom commands set up yet!')
            return
        
        embed = discord.Embed(title='Custom Commands', color=discord.Color.blue())
        for cmd in commands_list:
            embed.add_field(name=cmd['name'], value=cmd['response'][:1024], inline=False)
        await ctx.send(embed=embed)

@custom.command(name='add')
async def add_custom_command(ctx, name: str, *, response: str):
    if name in [c.name for c in bot.commands]:
        await ctx.send('❌ Cannot override built-in commands!')
        return
    
    if db.add_custom_command(ctx.guild.id, name, response):
        await ctx.send(f'✅ Added custom command: `{name}`')
    else:
        await ctx.send('❌ Command already exists!')

@custom.command(name='remove')
async def remove_custom_command(ctx, name: str):
    if db.remove_custom_command(ctx.guild.id, name):
        await ctx.send(f'✅ Removed custom command: `{name}`')
    else:
        await ctx.send('❌ Command not found!')

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Handle DMs for ModMail
    if not message.guild:
        thread = next((t for t in active_threads.values() if t.user_id == message.author.id), None)
        
        if not thread:
            # Create new thread
            category = discord.utils.get(bot.guilds[0].categories, name='ModMail')
            if not category:
                return
            
            channel = await category.create_text_channel(f'modmail-{message.author.name}')
            thread = ModMailThread(message.author.id, channel.id)
            active_threads[channel.id] = thread
            
            # Send initial thread info
            embed = create_thread_embed(thread, message.author)
            await channel.send(embed=embed)
        
        # Forward message to thread channel
        channel = bot.get_channel(thread.channel_id)
        embed = discord.Embed(
            description=message.content,
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        embed.set_author(name=f"{message.author.name}#{message.author.discriminator}")
        await channel.send(embed=embed)
        thread.add_log_entry(str(message.author), message.content)
        return

    if message.guild:
        # Check for custom commands
        settings = db.get_guild_settings(message.guild.id)
        prefix = settings['prefix']
        if message.content.startswith(prefix):
            cmd_name = message.content[len(prefix):].split()[0].lower()
            response = db.get_custom_command(message.guild.id, cmd_name)
            if response:
                await message.channel.send(response)
                return

    await bot.process_commands(message)

@bot.remove_command('help')

@bot.group(invoke_without_command=True)
async def help(ctx):
    embed = discord.Embed(
        title="📬 ModMail Bot Help",
        description="Welcome to ModMail Bot! Here are all available commands:\n\n**Note:** The bot prefix is `-`",
        color=discord.Color.blue()
    )

    # General Commands
    embed.add_field(
        name="📋 General Commands",
        value="```Simply DM the bot to create a ModMail thread!```",
        inline=False
    )

    # Moderator Commands
    mod_commands = (
        "🔧 **-reply <message>** - Reply to a ModMail thread\n"
        "🕵️ **-areply <message>** - Send an anonymous reply\n"
        "📝 **-close [reason]** - Close a ModMail thread\n"
        "📌 **-priority <low|medium|high|urgent>** - Set thread priority\n"
        "🏷️ **-category <general|support|report|appeal>** - Set thread category\n"
        "👤 **-assign <mod>** - Assign thread to a moderator\n"
        "⚠️ **-warn <user> <reason>** - Warn a user\n"
        "🔇 **-mute <user> <duration> <reason>** - Temporarily mute a user\n"
        "📜 **-history @user** - View user's moderation history\n"
        "🔍 **-case <case_id>** - View specific case details"
    )
    embed.add_field(
        name="🛡️ Moderator Commands",
        value=mod_commands,
        inline=False
    )

    # Snippet Commands
    snippet_commands = (
        "💾 **-snippet add <name> <content>** - Create a snippet\n"
        "📤 **-snippet use <name>** - Use a snippet in reply\n"
        "❌ **-snippet remove <name>** - Remove a snippet\n"
        "📋 **-snippet list** - List all snippets"
    )
    embed.add_field(
        name="📝 Snippet Commands",
        value=snippet_commands,
        inline=False
    )

    # Admin Commands
    admin_commands = (
        "⚙️ **-config** - View server configuration\n"
        "⛔ **-ban <user> <reason>** - Ban a user\n"
        "👢 **-kick <user> <reason>** - Kick a user\n"
        "🔧 **-custom** - Manage custom commands"
    )
    embed.add_field(
        name="⚡ Admin Commands",
        value=admin_commands,
        inline=False
    )

    # Footer with additional info
    embed.set_footer(text="For detailed help on a command, use -help <command>")
    
    await ctx.send(embed=embed)

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    
    # Create modmail category if it doesn't exist
    guild = bot.get_guild(int(os.getenv('GUILD_ID')))
    existing_category = discord.utils.get(guild.categories, name='ModMail')
    if not existing_category:
        await guild.create_category('ModMail')
    
    # Start mute expiry check loop
    bot.loop.create_task(check_mute_expiry())

@bot.event
async def on_message(message):
    # Ignore messages from the bot itself
    if message.author == bot.user:
        return

    # Handle DMs
    if isinstance(message.channel, discord.DMChannel):
        await handle_modmail_dm(message)
    
    await bot.process_commands(message)

async def handle_modmail_dm(message):
    if message.author.id in active_threads:
        # Forward message to existing thread
        thread_channel = bot.get_channel(active_threads[message.author.id])
        if thread_channel:
            embed = discord.Embed(
                description=message.content,
                color=discord.Color.blue(),
                timestamp=message.created_at
            )
            embed.set_author(name=f"{message.author}", icon_url=message.author.avatar.url if message.author.avatar else None)
            await thread_channel.send(embed=embed)
    else:
        # Create new thread
        guild = bot.get_guild(int(os.getenv('GUILD_ID')))
        category = discord.utils.get(guild.categories, name='ModMail')
        
        if category:
            channel = await guild.create_text_channel(
                f"modmail-{message.author.name}",
                category=category
            )
            active_threads[message.author.id] = channel.id
            
            # Send initial message
            embed = discord.Embed(
                title="New ModMail Thread",
                description=f"User: {message.author.mention}\nID: {message.author.id}\n\nMessage: {message.content}",
                color=discord.Color.green(),
                timestamp=message.created_at
            )
            embed.set_author(name=f"{message.author}", icon_url=message.author.avatar.url if message.author.avatar else None)
            await channel.send(embed=embed)
            
            # Confirm receipt to user
            await message.author.send("Your message has been sent to the moderators. They will respond shortly.")

@bot.command()
@commands.check(lambda ctx: has_mod_role(ctx))
async def reply(ctx, *, message):
    """Reply to a modmail thread"""
    if not ctx.channel.name.startswith('modmail-'):
        await ctx.send("This command can only be used in modmail channels!")
        return
    
    # Find the user ID from active threads
    user_id = None
    for uid, channel_id in active_threads.items():
        if channel_id == ctx.channel.id:
            user_id = uid
            break
    
    if user_id:
        user = await bot.fetch_user(user_id)
        try:
            embed = discord.Embed(
                description=message,
                color=discord.Color.green(),
                timestamp=ctx.message.created_at
            )
            embed.set_author(name=f"{ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
            await user.send(embed=embed)
            
            # Send confirmation in the modmail channel
            await ctx.send(f"✅ Message sent to {user}")
        except discord.Forbidden:
            await ctx.send("❌ Could not send message to the user. They might have blocked the bot or disabled DMs.")

@bot.command()
@commands.check(lambda ctx: has_mod_role(ctx))
async def close(ctx):
    """Close a modmail thread"""
    if not ctx.channel.name.startswith('modmail-'):
        await ctx.send("This command can only be used in modmail channels!")
        return
    
    # Find and remove the thread from active_threads
    user_id = None
    for uid, channel_id in active_threads.items():
        if channel_id == ctx.channel.id:
            user_id = uid
            break
    
    if user_id:
        del active_threads[user_id]
        user = await bot.fetch_user(user_id)
        try:
            await user.send("This modmail thread has been closed by the moderators.")
        except discord.Forbidden:
            pass
        
        await ctx.send("Thread closing in 5 seconds...")
        await asyncio.sleep(5)
        await ctx.channel.delete()

@bot.command()
@commands.check(lambda ctx: has_mod_role(ctx))
async def warn(ctx, user: discord.Member, *, reason: str):
    """Issue a warning to a user"""
    case_id = db.add_case(user.id, ctx.author.id, 'warn', reason)
    
    embed = discord.Embed(
        title="Warning",
        description=f"You have been warned in {ctx.guild.name}\nReason: {reason}",
        color=discord.Color.yellow()
    )
    try:
        await user.send(embed=embed)
    except discord.Forbidden:
        pass
    
    await ctx.send(f"✅ Warned {user.mention} | Case #{case_id}")

@bot.command()
@commands.check(lambda ctx: has_mod_role(ctx))
async def mute(ctx, user: discord.Member, duration: str, *, reason: str):
    """Temporarily mute a user"""
    minutes = parse_duration(duration)
    if not minutes:
        await ctx.send("❌ Invalid duration format. Use format: 1m, 1h, or 1d")
        return
    
    mute_role = discord.utils.get(ctx.guild.roles, name="Muted")
    if not mute_role:
        # Create mute role if it doesn't exist
        mute_role = await ctx.guild.create_role(name="Muted")
        for channel in ctx.guild.channels:
            await channel.set_permissions(mute_role, send_messages=False, add_reactions=False)
    
    await user.add_roles(mute_role)
    db.add_mute(user.id, ctx.guild.id, minutes)
    case_id = db.add_case(user.id, ctx.author.id, 'mute', reason, duration)
    
    embed = discord.Embed(
        title="Muted",
        description=f"You have been muted in {ctx.guild.name}\nDuration: {format_duration(minutes)}\nReason: {reason}",
        color=discord.Color.red()
    )
    try:
        await user.send(embed=embed)
    except discord.Forbidden:
        pass
    
    await ctx.send(f"✅ Muted {user.mention} for {format_duration(minutes)} | Case #{case_id}")

@bot.command()
@commands.check(lambda ctx: has_mod_role(ctx))
async def unmute(ctx, user: discord.Member):
    """Remove a user's mute"""
    mute_role = discord.utils.get(ctx.guild.roles, name="Muted")
    if mute_role in user.roles:
        await user.remove_roles(mute_role)
        db.remove_mute(user.id)
        case_id = db.add_case(user.id, ctx.author.id, 'unmute')
        await ctx.send(f"✅ Unmuted {user.mention} | Case #{case_id}")
    else:
        await ctx.send("❌ This user is not muted")

@bot.command()
@commands.check(lambda ctx: has_admin_role(ctx))
async def kick(ctx, user: discord.Member, *, reason: str):
    """Kick a user from the server"""
    case_id = db.add_case(user.id, ctx.author.id, 'kick', reason)
    
    embed = discord.Embed(
        title="Kicked",
        description=f"You have been kicked from {ctx.guild.name}\nReason: {reason}",
        color=discord.Color.red()
    )
    try:
        await user.send(embed=embed)
    except discord.Forbidden:
        pass
    
    await user.kick(reason=reason)
    await ctx.send(f"✅ Kicked {user.mention} | Case #{case_id}")

@bot.command()
@commands.check(lambda ctx: has_admin_role(ctx))
async def ban(ctx, user: discord.Member, days: int, *, reason: str):
    """Ban a user from the server"""
    case_id = db.add_case(user.id, ctx.author.id, 'ban', reason, f"{days}d")
    
    embed = discord.Embed(
        title="Banned",
        description=f"You have been banned from {ctx.guild.name}\nDuration: {days} days\nReason: {reason}",
        color=discord.Color.red()
    )
    try:
        await user.send(embed=embed)
    except discord.Forbidden:
        pass
    
    await user.ban(reason=reason, delete_message_days=min(days, 7))
    await ctx.send(f"✅ Banned {user.mention} | Case #{case_id}")

@bot.command()
@commands.check(lambda ctx: has_admin_role(ctx))
async def unban(ctx, user_id: int):
    """Unban a user from the server"""
    try:
        user = await bot.fetch_user(user_id)
        await ctx.guild.unban(user)
        case_id = db.add_case(user_id, ctx.author.id, 'unban')
        await ctx.send(f"✅ Unbanned {user.mention} | Case #{case_id}")
    except discord.NotFound:
        await ctx.send("❌ User not found")
    except discord.Forbidden:
        await ctx.send("❌ I don't have permission to unban users")

@bot.command()
@commands.check(lambda ctx: has_mod_role(ctx))
async def history(ctx, user: discord.Member):
    """View a user's moderation history"""
    cases = db.get_user_history(user.id)
    if not cases:
        await ctx.send(f"No moderation history found for {user.mention}")
        return
    
    embed = discord.Embed(
        title=f"Moderation History - {user}",
        color=discord.Color.blue()
    )
    
    for case in cases:
        moderator = await bot.fetch_user(case['moderator_id'])
        value = f"**Moderator:** {moderator.mention}\n"
        if case['reason']:
            value += f"**Reason:** {case['reason']}\n"
        if case['duration']:
            value += f"**Duration:** {case['duration']}\n"
        value += f"**Date:** {case['created_at']}"
        
        embed.add_field(
            name=f"Case #{case['case_id']} - {case['action_type'].upper()}",
            value=value,
            inline=False
        )
    
    await ctx.send(embed=embed)

@bot.command()
@commands.check(lambda ctx: has_mod_role(ctx))
async def case(ctx, case_id: int):
    """View details of a specific moderation case"""
    case = db.get_case(case_id)
    if not case:
        await ctx.send("❌ Case not found")
        return
    
    user = await bot.fetch_user(case['user_id'])
    moderator = await bot.fetch_user(case['moderator_id'])
    
    embed = discord.Embed(
        title=f"Case #{case_id} - {case['action_type'].upper()}",
        color=discord.Color.blue(),
        timestamp=discord.utils.parse_time(case['created_at'])
    )
    
    embed.add_field(name="User", value=f"{user.mention} ({user.id})")
    embed.add_field(name="Moderator", value=f"{moderator.mention} ({moderator.id})")
    if case['reason']:
        embed.add_field(name="Reason", value=case['reason'], inline=False)
    if case['duration']:
        embed.add_field(name="Duration", value=case['duration'])
    
    await ctx.send(embed=embed)

async def check_mute_expiry():
    """Check for expired mutes and remove them"""
    while True:
        expired_mutes = db.get_expired_mutes()
        for mute in expired_mutes:
            guild = bot.get_guild(mute['guild_id'])
            if guild:
                member = guild.get_member(mute['user_id'])
                if member:
                    mute_role = discord.utils.get(guild.roles, name="Muted")
                    if mute_role and mute_role in member.roles:
                        await member.remove_roles(mute_role)
                        db.remove_mute(member.id)
        
        await asyncio.sleep(60)  # Check every minute

# Run the bot
bot.run(os.getenv('DISCORD_TOKEN'))
