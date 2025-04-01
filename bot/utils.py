from typing import Optional, Tuple, Dict, List
import re
import discord
from discord.ext import commands
import os
from enum import Enum
from datetime import datetime

class ThreadPriority(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    URGENT = 4

class ThreadCategory(Enum):
    GENERAL = "general"
    SUPPORT = "support"
    REPORT = "report"
    APPEAL = "appeal"

class ThreadStatus(Enum):
    OPEN = "open"
    PENDING = "pending"
    CLOSED = "closed"

class ModMailThread:
    def __init__(self, user_id: int, channel_id: int):
        self.user_id = user_id
        self.channel_id = channel_id
        self.created_at = datetime.now()
        self.last_updated = datetime.now()
        self.status = ThreadStatus.OPEN
        self.priority = ThreadPriority.MEDIUM
        self.category = ThreadCategory.GENERAL
        self.assigned_mod = None
        self.is_anonymous = False
        self.log_entries = []

    def update(self):
        self.last_updated = datetime.now()

    def add_log_entry(self, author: str, content: str, is_anonymous: bool = False):
        entry = {
            'author': 'Staff' if is_anonymous else author,
            'content': content,
            'timestamp': datetime.now(),
            'is_anonymous': is_anonymous
        }
        self.log_entries.append(entry)

class SnippetManager:
    def __init__(self):
        self.snippets: Dict[int, Dict[str, str]] = {}

    def add_snippet(self, guild_id: int, name: str, content: str) -> bool:
        if guild_id not in self.snippets:
            self.snippets[guild_id] = {}
        
        if name in self.snippets[guild_id]:
            return False
        
        self.snippets[guild_id][name] = content
        return True

    def get_snippet(self, guild_id: int, name: str) -> Optional[str]:
        return self.snippets.get(guild_id, {}).get(name)

    def remove_snippet(self, guild_id: int, name: str) -> bool:
        if guild_id in self.snippets and name in self.snippets[guild_id]:
            del self.snippets[guild_id][name]
            return True
        return False

    def list_snippets(self, guild_id: int) -> List[str]:
        return list(self.snippets.get(guild_id, {}).keys())

def create_thread_embed(thread: ModMailThread, user: discord.User) -> discord.Embed:
    # Set color based on priority
    priority_colors = {
        ThreadPriority.LOW: discord.Color.green(),
        ThreadPriority.MEDIUM: discord.Color.blue(),
        ThreadPriority.HIGH: discord.Color.orange(),
        ThreadPriority.URGENT: discord.Color.red()
    }
    
    embed = discord.Embed(
        title=f"ModMail Thread - {user.name}#{user.discriminator}",
        color=priority_colors.get(thread.priority, discord.Color.blue())
    )
    
    embed.add_field(
        name="Status",
        value=thread.status.value.title(),
        inline=True
    )
    embed.add_field(
        name="Priority",
        value=thread.priority.name.title(),
        inline=True
    )
    embed.add_field(
        name="Category",
        value=thread.category.value.title(),
        inline=True
    )
    
    if thread.assigned_mod:
        embed.add_field(
            name="Assigned Moderator",
            value=thread.assigned_mod,
            inline=True
        )
    
    embed.set_footer(text=f"Created at {thread.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
    return embed

def parse_duration(duration_str: str) -> Optional[int]:
    """Convert duration string (e.g., '1h', '30m', '2d') to minutes"""
    if not duration_str:
        return None
    
    match = re.match(r'^(\d+)([mhd])$', duration_str.lower())
    if not match:
        return None
    
    amount = int(match.group(1))
    unit = match.group(2)
    
    if unit == 'm':
        return amount
    elif unit == 'h':
        return amount * 60
    elif unit == 'd':
        return amount * 24 * 60
    return None

def is_owner(user_id: int) -> bool:
    owner_id = os.getenv('OWNER_ID')
    return str(user_id) == owner_id if owner_id else False

def has_mod_role(member: discord.Member) -> bool:
    if is_owner(member.id):
        return True
    mod_role_id = os.getenv('MOD_ROLE_ID')
    return any(role.id == int(mod_role_id) for role in member.roles) if mod_role_id else False

def has_admin_role(member: discord.Member) -> bool:
    if is_owner(member.id):
        return True
    admin_role_id = os.getenv('ADMIN_ROLE_ID')
    return any(role.id == int(admin_role_id) for role in member.roles) if admin_role_id else False

def format_duration(minutes: int) -> str:
    """Format duration in minutes to a human-readable string"""
    if minutes < 60:
        return f"{minutes}m"
    elif minutes < 1440:
        hours = minutes // 60
        mins = minutes % 60
        return f"{hours}h {mins}m" if mins else f"{hours}h"
    else:
        days = minutes // 1440
        hours = (minutes % 1440) // 60
        mins = minutes % 60
        if hours == 0 and mins == 0:
            return f"{days}d"
        elif mins == 0:
            return f"{days}d {hours}h"
        else:
            return f"{days}d {hours}h {mins}m"