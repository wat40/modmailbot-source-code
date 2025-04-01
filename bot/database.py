import sqlite3
import datetime
from typing import Optional, List, Dict

class Database:
    def __init__(self, db_path: str = 'moderation.db'):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            # Create cases table for storing moderation actions
            c.execute('''
                CREATE TABLE IF NOT EXISTS cases (
                    case_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    moderator_id INTEGER NOT NULL,
                    action_type TEXT NOT NULL,
                    reason TEXT,
                    duration TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create active_mutes table for tracking temporary mutes
            c.execute('''
                CREATE TABLE IF NOT EXISTS active_mutes (
                    user_id INTEGER PRIMARY KEY,
                    guild_id INTEGER NOT NULL,
                    end_time TIMESTAMP NOT NULL
                )
            ''')

            # Create guild_settings table for server-specific configurations
            c.execute('''
                CREATE TABLE IF NOT EXISTS guild_settings (
                    guild_id INTEGER PRIMARY KEY,
                    prefix TEXT DEFAULT "!",
                    welcome_channel_id INTEGER,
                    welcome_message TEXT,
                    modmail_category TEXT DEFAULT "ModMail",
                    auto_role_id INTEGER,
                    log_channel_id INTEGER
                )
            ''')

            # Create custom_commands table for server-specific custom commands
            c.execute('''
                CREATE TABLE IF NOT EXISTS custom_commands (
                    command_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    command_name TEXT NOT NULL,
                    response TEXT NOT NULL,
                    UNIQUE(guild_id, command_name)
                )
            ''')
            conn.commit()
    
    def add_case(self, user_id: int, moderator_id: int, action_type: str,
                 reason: Optional[str] = None, duration: Optional[str] = None) -> int:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO cases (user_id, moderator_id, action_type, reason, duration)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, moderator_id, action_type, reason, duration))
            conn.commit()
            return c.lastrowid
    
    def get_case(self, case_id: int) -> Optional[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM cases WHERE case_id = ?', (case_id,))
            result = c.fetchone()
            if result:
                return {
                    'case_id': result[0],
                    'user_id': result[1],
                    'moderator_id': result[2],
                    'action_type': result[3],
                    'reason': result[4],
                    'duration': result[5],
                    'created_at': result[6]
                }
            return None
    
    def get_user_history(self, user_id: int) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM cases WHERE user_id = ? ORDER BY created_at DESC', (user_id,))
            results = c.fetchall()
            return [{
                'case_id': r[0],
                'user_id': r[1],
                'moderator_id': r[2],
                'action_type': r[3],
                'reason': r[4],
                'duration': r[5],
                'created_at': r[6]
            } for r in results]
    
    def add_mute(self, user_id: int, guild_id: int, duration_minutes: int):
        end_time = datetime.datetime.now() + datetime.timedelta(minutes=duration_minutes)
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('''
                INSERT OR REPLACE INTO active_mutes (user_id, guild_id, end_time)
                VALUES (?, ?, ?)
            ''', (user_id, guild_id, end_time))
            conn.commit()
    
    def remove_mute(self, user_id: int):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('DELETE FROM active_mutes WHERE user_id = ?', (user_id,))
            conn.commit()
    
    def get_expired_mutes(self) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('''
                SELECT user_id, guild_id FROM active_mutes
                WHERE end_time <= CURRENT_TIMESTAMP
            ''')
            return [{'user_id': r[0], 'guild_id': r[1]} for r in c.fetchall()]
    
    # Guild Settings Methods
    def get_guild_settings(self, guild_id: int) -> Dict:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM guild_settings WHERE guild_id = ?', (guild_id,))
            result = c.fetchone()
            if result:
                return {
                    'guild_id': result[0],
                    'prefix': result[1],
                    'welcome_channel_id': result[2],
                    'welcome_message': result[3],
                    'modmail_category': result[4],
                    'auto_role_id': result[5],
                    'log_channel_id': result[6]
                }
            # Insert default settings if none exist
            c.execute('INSERT INTO guild_settings (guild_id) VALUES (?)', (guild_id,))
            conn.commit()
            return self.get_guild_settings(guild_id)
    
    def update_guild_setting(self, guild_id: int, setting: str, value: any):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute(f'UPDATE guild_settings SET {setting} = ? WHERE guild_id = ?', (value, guild_id))
            conn.commit()
    
    # Custom Commands Methods
    def add_custom_command(self, guild_id: int, command_name: str, response: str) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                c = conn.cursor()
                c.execute('''
                    INSERT INTO custom_commands (guild_id, command_name, response)
                    VALUES (?, ?, ?)
                ''', (guild_id, command_name.lower(), response))
                conn.commit()
                return True
        except sqlite3.IntegrityError:
            return False
    
    def remove_custom_command(self, guild_id: int, command_name: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('DELETE FROM custom_commands WHERE guild_id = ? AND command_name = ?',
                      (guild_id, command_name.lower()))
            return c.rowcount > 0
    
    def get_custom_commands(self, guild_id: int) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('SELECT command_name, response FROM custom_commands WHERE guild_id = ?', (guild_id,))
            return [{'name': r[0], 'response': r[1]} for r in c.fetchall()]
    
    def get_custom_command(self, guild_id: int, command_name: str) -> Optional[str]:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('SELECT response FROM custom_commands WHERE guild_id = ? AND command_name = ?',
                      (guild_id, command_name.lower()))
            result = c.fetchone()
            return result[0] if result else None