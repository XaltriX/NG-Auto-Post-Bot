from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackQueryHandler, ContextTypes
import logging
import json
import os
import warnings
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from typing import Dict, List, Optional

# Suppress PTB warnings
warnings.filterwarnings('ignore', category=UserWarning, module='telegram')

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Constants
THUMBNAIL, VIDEO_LINK, BOT_SELECTION, ADDING_CHANNEL, SCHEDULE_OR_POST_NOW, SCHEDULE_TIME, CONFIRM_ANOTHER = range(7)

CHANNELS_FILE = 'channels.json'
SCHEDULED_POSTS_FILE = 'scheduled_posts.json'
MAX_POSTED_HISTORY = 5  # Show only last 5 posted items

BOT_TUTORIALS = {
    'xrated': 'https://t.me/TutorialsNG/11',
    'nightrider': 'https://t.me/TutorialsNG/10'
}

DECORATIVE_LINES = {
    'top': "══════⊹⊱≼≽⊰⊹══════",
    'middle': "◃───────────▹",
    'bottom': "⫘⫘⫘⫘⫘⫘⫘⫘⫘⫘"
}

# Global storage
user_data: Dict = {}
scheduler = AsyncIOScheduler()


# ============== UTILITY FUNCTIONS ==============

def load_json(filename: str) -> Dict:
    """Load JSON data from file"""
    if os.path.exists(filename):
        try:
            with open(filename, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            logger.error(f"Error loading {filename}, returning empty dict")
    return {}


def save_json(filename: str, data: Dict) -> None:
    """Save data to JSON file"""
    try:
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving {filename}: {e}")


def escape_markdown(text: str) -> str:
    """Escape special characters for MarkdownV2"""
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text


def create_post_text(video_link: str, tutorial_link: str) -> str:
    """Create formatted post text"""
    return (
        f"{DECORATIVE_LINES['top']}\n\n"
        f"*🎬 VIDEO LINK:*\n"
        f"_{video_link}_\n\n"
        f"{DECORATIVE_LINES['middle']}\n\n"
        f"*📥 HOW TO DOWNLOAD AND WATCH VIDEO:*\n"
        f"_{escape_markdown(tutorial_link)}_\n\n"
        f"{DECORATIVE_LINES['bottom']}\n\n"
        f"*Made by \\- @Neonghost\\_Network* 🌟"
    )


async def verify_channel_access(context: ContextTypes.DEFAULT_TYPE, channel_id: str) -> Optional[tuple]:
    """Verify bot has access to channel. Returns (chat, can_post) or None"""
    try:
        chat = await context.bot.get_chat(channel_id)
        bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
        return (chat, bot_member.can_post_messages)
    except Exception as e:
        logger.error(f"Error verifying channel {channel_id}: {e}")
        return None


# ============== KEYBOARD HELPERS ==============

def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Return main menu keyboard"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Create New Post", callback_data='create_post')],
        [InlineKeyboardButton("📺 Manage Channels", callback_data='manage_channels')],
        [InlineKeyboardButton("📅 Check Scheduled Posts", callback_data='check_scheduled')],
        [InlineKeyboardButton("❓ Help", callback_data='help')]
    ])


def channel_management_keyboard() -> InlineKeyboardMarkup:
    """Return channel management keyboard"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Channel", callback_data='add_channel')],
        [InlineKeyboardButton("📄 List Channels", callback_data='list_channels')],
        [InlineKeyboardButton("🏠 Main Menu", callback_data='main_menu')]
    ])


def bot_selection_keyboard() -> InlineKeyboardMarkup:
    """Return bot selection keyboard"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔞 X-Rated Bot", callback_data='xrated')],
        [InlineKeyboardButton("🌙 Night Rider Bot", callback_data='nightrider')],
        [InlineKeyboardButton("🏠 Main Menu", callback_data='main_menu')]
    ])


def schedule_keyboard() -> InlineKeyboardMarkup:
    """Return schedule options keyboard"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Post Now", callback_data='post_now')],
        [InlineKeyboardButton("📅 Schedule", callback_data='schedule')],
        [InlineKeyboardButton("🏠 Main Menu", callback_data='main_menu')]
    ])


# ============== COMMAND HANDLERS ==============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command - show main menu"""
    message = "👋 Welcome to the Post Generator Bot!\nWhat would you like to do?"
    
    if update.callback_query:
        await update.callback_query.message.edit_text(message, reply_markup=main_menu_keyboard())
    else:
        await update.message.reply_text(message, reply_markup=main_menu_keyboard())
    
    return ConversationHandler.END


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help message"""
    help_text = (
        "🤖 *Post Generator Bot Help*\n\n"
        "1️⃣ *Create New Post*: Generate posts with thumbnail and video link\n"
        "2️⃣ *Manage Channels*: Add or list your channels\n"
        "3️⃣ *Check Scheduled Posts*: View upcoming and recent posts\n"
        "4️⃣ *Help*: Show this message\n\n"
        "Use the buttons to navigate through features\\."
    )
    
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data='main_menu')]])
    
    if update.callback_query:
        await update.callback_query.message.edit_text(help_text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN_V2)
    else:
        await update.message.reply_text(help_text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN_V2)
    
    return ConversationHandler.END


# ============== CHANNEL MANAGEMENT ==============

async def manage_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show channel management options"""
    message = "📺 *Channel Management*\n\nWhat would you like to do?"
    
    if update.callback_query:
        await update.callback_query.message.edit_text(
            message, 
            reply_markup=channel_management_keyboard(),
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(
            message,
            reply_markup=channel_management_keyboard(),
            parse_mode=ParseMode.MARKDOWN
        )
    
    return ConversationHandler.END


async def add_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add a new channel"""
    message = update.message
    user_id = str(message.from_user.id)
    
    # Extract channel ID
    channel_id = None
    if hasattr(message, 'forward_from_chat') and message.forward_from_chat:
        channel_id = str(message.forward_from_chat.id)
    else:
        try:
            channel_id = str(int(message.text))
        except ValueError:
            await message.reply_text(
                "⚠️ *Invalid input\\!*\n"
                "Please forward a message from the channel or send a valid channel ID\\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return ADDING_CHANNEL
    
    # Verify channel access
    verification = await verify_channel_access(context, channel_id)
    if not verification:
        await message.reply_text(
            "❌ *Cannot access this channel\\!*\n"
            "Make sure:\n"
            "1\\. Channel ID is correct\n"
            "2\\. Bot is added as admin\n"
            "3\\. Bot has posting permissions",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return ADDING_CHANNEL
    
    chat, can_post = verification
    if not can_post:
        await message.reply_text(
            "⚠️ *No posting permission\\!*\n"
            "Please grant the bot permission to post messages\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return ADDING_CHANNEL
    
    # Save channel
    channels = load_json(CHANNELS_FILE)
    if user_id not in channels:
        channels[user_id] = []
    
    if channel_id not in channels[user_id]:
        channels[user_id].append(channel_id)
        save_json(CHANNELS_FILE, channels)
        await message.reply_text(
            f"✅ Channel *{escape_markdown(chat.title)}* added successfully\\!",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    else:
        await message.reply_text("ℹ️ This channel is already in your list\\.", parse_mode=ParseMode.MARKDOWN_V2)
    
    await message.reply_text(
        "*What would you like to do next?*",
        reply_markup=channel_management_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )
    
    return ConversationHandler.END


async def list_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all user channels"""
    user_id = str(update.callback_query.from_user.id if update.callback_query else update.message.from_user.id)
    message = update.callback_query.message if update.callback_query else update.message
    
    channels = load_json(CHANNELS_FILE)
    user_channels = channels.get(user_id, [])
    
    if not user_channels:
        text = (
            "📭 *No channels added yet\\!*\n"
            "Use the 'Add Channel' option to get started\\."
        )
        if update.callback_query:
            await message.edit_text(text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=channel_management_keyboard())
        else:
            await message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=channel_management_keyboard())
        return ConversationHandler.END
    
    # Build channel list
    channel_list = ["📄 *Your Channels:*\n"]
    for channel_id in user_channels:
        verification = await verify_channel_access(context, channel_id)
        if verification:
            chat, can_post = verification
            status = "✅ Active" if can_post else "⚠️ No Post Permission"
            channel_list.append(
                f"📺 *{escape_markdown(chat.title)}*\n"
                f"   ID: `{channel_id}`\n"
                f"   Status: {status}\n"
            )
        else:
            channel_list.append(
                f"❌ *Inaccessible Channel*\n"
                f"   ID: `{channel_id}`\n"
                f"   Bot may have been removed\n"
            )
    
    text = "\n".join(channel_list)
    
    if update.callback_query:
        await message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
    else:
        await message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
    
    await message.reply_text(
        "*What would you like to do next?*",
        reply_markup=channel_management_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )
    
    return ConversationHandler.END


# ============== POST CREATION ==============

async def thumbnail_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle received thumbnail"""
    message = update.message
    user_id = message.from_user.id
    
    # Extract file info
    if message.photo:
        file_id, file_type = message.photo[-1].file_id, "photo"
    elif message.video:
        file_id, file_type = message.video.file_id, "video"
    elif message.animation:
        file_id, file_type = message.animation.file_id, "animation"
    else:
        await message.reply_text("⚠️ Please send a valid image, video, or GIF\\.", parse_mode=ParseMode.MARKDOWN_V2)
        return THUMBNAIL
    
    user_data[user_id] = {"thumbnail_id": file_id, "thumbnail_type": file_type}
    await message.reply_text("👍 Great\\! Now send me the video link\\.", parse_mode=ParseMode.MARKDOWN_V2)
    
    return VIDEO_LINK


async def video_link_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle video link and ask for bot selection"""
    user_id = update.message.from_user.id
    user_data[user_id]["video_link"] = escape_markdown(update.message.text)
    
    await update.message.reply_text(
        "*Select which bot to use:*",
        reply_markup=bot_selection_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )
    
    return BOT_SELECTION


async def schedule_post_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask whether to post now or schedule"""
    await update.callback_query.message.edit_text(
        "*Post now or schedule?*",
        reply_markup=schedule_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )
    return SCHEDULE_OR_POST_NOW


# ============== POSTING ==============

async def post_to_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Post immediately to all channels"""
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    
    channels = load_json(CHANNELS_FILE)
    user_channels = channels.get(user_id, [])
    
    if not user_channels:
        await query.message.reply_text(
            "❌ *No channels added\\!*\n"
            "Please add channels first\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return ConversationHandler.END
    
    # Prepare post data
    post_data = user_data.get(int(user_id))
    if not post_data:
        await query.message.reply_text(
            "❌ *Session expired\\!*\nPlease start again\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return ConversationHandler.END
    
    tutorial_link = BOT_TUTORIALS[post_data['bot_type']]
    post_text = create_post_text(post_data['video_link'], tutorial_link)
    
    # Post to channels
    success, failed = [], []
    for channel_id in user_channels:
        try:
            send_method = {
                "photo": context.bot.send_photo,
                "video": context.bot.send_video,
                "animation": context.bot.send_animation
            }[post_data["thumbnail_type"]]
            
            media_key = {
                "photo": "photo",
                "video": "video",
                "animation": "animation"
            }[post_data["thumbnail_type"]]
            
            await send_method(
                chat_id=channel_id,
                **{media_key: post_data["thumbnail_id"]},
                caption=post_text,
                parse_mode=ParseMode.MARKDOWN_V2
            )
            success.append(channel_id)
            logger.info(f"Posted to channel {channel_id}")
        except Exception as e:
            failed.append(channel_id)
            logger.error(f"Failed to post to {channel_id}: {e}")
    
    # Build status message with proper escaping
    status = f"*📊 Post Status:*\n\n✅ *Posted to {len(success)}/{len(user_channels)} channels*"
    if failed:
        status += f"\n\n❌ Failed: {len(failed)} channel\\(s\\)"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Create Another", callback_data='create_post')],
        [InlineKeyboardButton("🏠 Main Menu", callback_data='main_menu')]
    ])
    
    await query.message.reply_text(status, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN_V2)
    
    # Cleanup
    user_data.pop(int(user_id), None)
    return ConversationHandler.END


# ============== SCHEDULING ==============

async def schedule_time_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Schedule post for specified time"""
    user_id = str(update.message.from_user.id)
    
    # Check if user data exists
    if int(user_id) not in user_data:
        await update.message.reply_text(
            "❌ *Session expired\\!*\nPlease start again with /start",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return ConversationHandler.END
    
    try:
        schedule_time = datetime.strptime(update.message.text.strip(), "%H:%M").time()
        now = datetime.now()
        schedule_datetime = datetime.combine(now.date(), schedule_time)
        
        if schedule_datetime < now:
            schedule_datetime += timedelta(days=1)
        
        # Prepare post data
        channels = load_json(CHANNELS_FILE)
        user_channels = channels.get(user_id, [])
        
        if not user_channels:
            await update.message.reply_text(
                "❌ *No channels added\\!*\n"
                "Please add channels first\\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return ConversationHandler.END
        
        post_data = user_data[int(user_id)].copy()
        post_data.update({
            "time": schedule_datetime.strftime("%Y-%m-%d %H:%M:%S"),
            "tutorial_link": BOT_TUTORIALS[post_data['bot_type']],
            "status": "⏳ Pending",
            "channels": user_channels,
            "user_id": user_id
        })
        
        # Save scheduled post
        scheduled_posts = load_json(SCHEDULED_POSTS_FILE)
        if user_id not in scheduled_posts:
            scheduled_posts[user_id] = []
        scheduled_posts[user_id].append(post_data)
        save_json(SCHEDULED_POSTS_FILE, scheduled_posts)
        
        # Schedule job
        scheduler.add_job(
            post_scheduled,
            'date',
            run_date=schedule_datetime,
            args=[context, post_data],
            id=f"post_{user_id}_{schedule_datetime.timestamp()}"
        )
        
        await update.message.reply_text(
            f"✅ *Post scheduled\\!*\n\n"
            f"📅 {schedule_datetime.strftime('%Y\\-%m\\-%d')}\n"
            f"⏰ {schedule_datetime.strftime('%H:%M')} IST\n"
            f"📺 {len(user_channels)} channel\\(s\\)",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 Schedule Another", callback_data='create_post')],
            [InlineKeyboardButton("📊 View Scheduled", callback_data='check_scheduled')],
            [InlineKeyboardButton("🏠 Main Menu", callback_data='main_menu')]
        ])
        
        await update.message.reply_text(
            "*Schedule another post?*",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Cleanup user data
        user_data.pop(int(user_id), None)
        
        return CONFIRM_ANOTHER
        
    except ValueError:
        await update.message.reply_text(
            "⚠️ *Invalid time format\\!*\n"
            "Use HH:MM format \\(e\\.g\\., `14:30`\\)",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return SCHEDULE_TIME
    except Exception as e:
        logger.error(f"Error scheduling post: {e}")
        await update.message.reply_text(
            "❌ *Error scheduling post\\!*\n"
            "Please try again\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return ConversationHandler.END


async def post_scheduled(context: ContextTypes.DEFAULT_TYPE, post_data: dict):
    """Execute scheduled post"""
    try:
        post_text = create_post_text(post_data['video_link'], post_data['tutorial_link'])
        success, failed = [], []
        
        for channel_id in post_data['channels']:
            try:
                send_method = {
                    "photo": context.bot.send_photo,
                    "video": context.bot.send_video,
                    "animation": context.bot.send_animation
                }[post_data["thumbnail_type"]]
                
                media_key = {
                    "photo": "photo",
                    "video": "video",
                    "animation": "animation"
                }[post_data["thumbnail_type"]]
                
                await send_method(
                    chat_id=channel_id,
                    **{media_key: post_data["thumbnail_id"]},
                    caption=post_text,
                    parse_mode=ParseMode.MARKDOWN_V2
                )
                success.append(channel_id)
                logger.info(f"Scheduled post delivered to {channel_id}")
            except Exception as e:
                failed.append(channel_id)
                logger.error(f"Scheduled post failed for {channel_id}: {e}")
        
        # Update status
        scheduled_posts = load_json(SCHEDULED_POSTS_FILE)
        user_id = post_data['user_id']
        
        if user_id in scheduled_posts:
            for post in scheduled_posts[user_id]:
                if post['time'] == post_data['time']:
                    post['status'] = f"✅ Posted ({len(success)}/{len(post_data['channels'])})"
            save_json(SCHEDULED_POSTS_FILE, scheduled_posts)
        
        # Notify user with proper escaping
        status = f"*📊 Scheduled Post Complete\\!*\n\n✅ Posted to {len(success)} channel\\(s\\)"
        if failed:
            status += f"\n❌ Failed: {len(failed)} channel\\(s\\)"
        
        try:
            await context.bot.send_message(
                chat_id=int(user_id),
                text=status,
                parse_mode=ParseMode.MARKDOWN_V2
            )
        except Exception as e:
            logger.error(f"Failed to notify user {user_id}: {e}")
        
    except Exception as e:
        logger.error(f"Error in post_scheduled: {e}")


async def check_scheduled_posts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check scheduled posts - show only last 5 posted"""
    user_id = str(update.callback_query.from_user.id if update.callback_query else update.message.from_user.id)
    scheduled_posts = load_json(SCHEDULED_POSTS_FILE).get(user_id, [])
    
    if not scheduled_posts:
        message = "*📊 No scheduled posts\\!*\n\nWould you like to create one?"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 Create Post", callback_data='create_post')],
            [InlineKeyboardButton("🏠 Main Menu", callback_data='main_menu')]
        ])
    else:
        now = datetime.now()
        
        # Filter posts
        posted = [p for p in scheduled_posts if datetime.strptime(p['time'], "%Y-%m-%d %H:%M:%S") < now and p.get('status', '').startswith('✅')]
        pending = [p for p in scheduled_posts if datetime.strptime(p['time'], "%Y-%m-%d %H:%M:%S") >= now]
        
        # Show only last 5 posted
        posted = sorted(posted, key=lambda x: x['time'], reverse=True)[:MAX_POSTED_HISTORY]
        pending = sorted(pending, key=lambda x: x['time'])
        
        message = "*📊 Scheduled Posts*\n\n"
        
        if posted:
            message += "*Recently Posted:*\n"
            for post in posted:
                dt = datetime.strptime(post['time'], "%Y-%m-%d %H:%M:%S")
                # Escape status message properly
                status = post['status'].replace('(', '\\(').replace(')', '\\)')
                message += f"• {status}\n  📅 {dt.strftime('%Y\\-%m\\-%d %H:%M')} IST\n"
        
        if pending:
            if posted:
                message += "\n"
            message += "*Pending:*\n"
            for post in pending:
                dt = datetime.strptime(post['time'], "%Y-%m-%d %H:%M:%S")
                message += f"• ⏳ Scheduled\n  📅 {dt.strftime('%Y\\-%m\\-%d %H:%M')} IST\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 Schedule New", callback_data='create_post')],
            [InlineKeyboardButton("🏠 Main Menu", callback_data='main_menu')]
        ])
    
    target = update.callback_query.message if update.callback_query else update.message
    
    # Use edit_text for callback queries to avoid duplicate messages
    if update.callback_query:
        await target.edit_text(message, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN_V2)
    else:
        await target.reply_text(message, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN_V2)
    
    return ConversationHandler.END


# ============== CALLBACK HANDLERS ==============

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all button callbacks"""
    query = update.callback_query
    await query.answer()
    
    # Handle bot selection
    if query.data in ['xrated', 'nightrider']:
        user_data[query.from_user.id]['bot_type'] = query.data
        return await schedule_post_prompt(update, context)
    
    # Handle post now
    if query.data == 'post_now':
        return await post_to_channels(update, context)
    
    # Handle schedule
    if query.data == 'schedule':
        await query.message.reply_text(
            "⏰ *Enter time to schedule \\(HH:MM format, IST\\)*\n"
            "Example: `14:30`",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return SCHEDULE_TIME
    
    # Handle create post
    if query.data == 'create_post':
        await query.message.reply_text(
            "🖼️ *Send me a thumbnail \\(image, video, or GIF\\)\\.*",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return THUMBNAIL
    
    # Handle add channel
    if query.data == 'add_channel':
        await query.message.reply_text(
            "📢 *Forward a message from the channel or send the channel ID\\.*",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return ADDING_CHANNEL
    
    # Handle other menu options
    if query.data == 'manage_channels':
        return await manage_channels(update, context)
    elif query.data == 'list_channels':
        return await list_channels(update, context)
    elif query.data == 'check_scheduled':
        return await check_scheduled_posts(update, context)
    elif query.data == 'help':
        return await help_command(update, context)
    elif query.data == 'main_menu':
        return await start(update, context)
    elif query.data == 'cancel':
        return await cancel(update, context)
    
    return ConversationHandler.END


async def schedule_or_post_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle schedule or post now choice"""
    return await button_handler(update, context)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel current operation"""
    user_id = update.effective_user.id
    user_data.pop(user_id, None)
    
    message = "❌ *Cancelled\\.*\nSend /start to begin again\\."
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.edit_text(message, parse_mode=ParseMode.MARKDOWN_V2)
    else:
        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)
    
    return ConversationHandler.END


# ============== ERROR HANDLER ==============

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors and notify user"""
    logger.error(f"Exception while handling update: {context.error}")
    
    # Try to notify user about the error
    if isinstance(update, Update) and update.effective_message:
        try:
            error_message = (
                "❌ *An error occurred\\!*\n\n"
                "Please try again or use /start to restart\\."
            )
            await update.effective_message.reply_text(
                error_message,
                parse_mode=ParseMode.MARKDOWN_V2
            )
        except Exception as e:
            logger.error(f"Failed to send error message: {e}")


# ============== MAIN ==============

def main():
    """Initialize and run bot"""
    TOKEN = '7907090935:AAEe-fnCgvwo583jL22VwSwJFxrFXEkJR_U'
    
    application = Application.builder().token(TOKEN).build()
    
    # Conversation handler
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start),
            CallbackQueryHandler(button_handler)
        ],
        states={
            THUMBNAIL: [
                MessageHandler(filters.PHOTO | filters.VIDEO | filters.ANIMATION, thumbnail_received),
                CommandHandler('cancel', cancel),
                CallbackQueryHandler(button_handler)
            ],
            VIDEO_LINK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, video_link_received),
                CommandHandler('cancel', cancel),
                CallbackQueryHandler(button_handler)
            ],
            BOT_SELECTION: [
                CallbackQueryHandler(button_handler),
                CommandHandler('cancel', cancel)
            ],
            SCHEDULE_OR_POST_NOW: [
                CallbackQueryHandler(schedule_or_post_now)
            ],
            SCHEDULE_TIME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, schedule_time_received),
                CommandHandler('cancel', cancel)
            ],
            CONFIRM_ANOTHER: [
                CallbackQueryHandler(button_handler)
            ],
            ADDING_CHANNEL: [
                MessageHandler(filters.TEXT | filters.FORWARDED, add_channel),
                CommandHandler('cancel', cancel),
                CallbackQueryHandler(button_handler)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        per_message=False,
        per_chat=True,
        per_user=True,
    )
    
    application.add_handler(conv_handler)
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    # Start scheduler
    scheduler.start()
    
    logger.info("✨ Bot started successfully!")
    print("🤖 Bot is running... Press Ctrl+C to stop.")
    
    application.run_polling()


if __name__ == '__main__':
    main()
