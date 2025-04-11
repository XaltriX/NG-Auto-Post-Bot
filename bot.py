from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackQueryHandler, ContextTypes
import logging
import json
import os
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram.error import TimedOut, NetworkError

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# States for conversation
THUMBNAIL, VIDEO_LINK, BOT_SELECTION, ADDING_CHANNEL, SCHEDULE_OR_POST_NOW, SCHEDULE_TIME, CONFIRM_ANOTHER = range(7)

# Store user data temporarily
user_data = {}

# Files to store data
CHANNELS_FILE = 'channels.json'
SCHEDULED_POSTS_FILE = 'scheduled_posts.json'

# Tutorial links for different bots
BOT_TUTORIALS = {
    'xrated': 'https://t.me/TutorialsNG/11',
    'nightrider': 'https://t.me/TutorialsNG/10'
}

# Decorative lines
DECORATIVE_LINES = [
    "══════⊹⊱≼≽⊰⊹══════",
    "____________",
    "◃───────────▹",
    "⫘⫘⫘⫘⫘⫘⫘⫘⫘⫘"
]

# Scheduler
scheduler = AsyncIOScheduler()

def load_channels():
    """Load channels from file"""
    if os.path.exists(CHANNELS_FILE):
        with open(CHANNELS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_channels(channels):
    """Save channels to file"""
    with open(CHANNELS_FILE, 'w') as f:
        json.dump(channels, f)

def load_scheduled_posts():
    """Load scheduled posts from file"""
    if os.path.exists(SCHEDULED_POSTS_FILE):
        with open(SCHEDULED_POSTS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_scheduled_posts(posts_data):
    """Save scheduled posts to file"""
    with open(SCHEDULED_POSTS_FILE, 'w') as f:
        json.dump(posts_data, f)

def escape_markdown(text):
    """Helper function to escape special characters for MarkdownV2"""
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the conversation with options"""
    keyboard = [
        [InlineKeyboardButton("📝 Create New Post", callback_data='create_post')],
        [InlineKeyboardButton("📺 Manage Channels", callback_data='manage_channels')],
        [InlineKeyboardButton("📅 Check Scheduled Posts", callback_data='check_scheduled')],
        [InlineKeyboardButton("❓ Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message = (
        "👋 Welcome to the Post Generator Bot!\n"
        "What would you like to do? 😊"
    )

    if update.callback_query:
        await update.callback_query.message.edit_text(message, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(message, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

    return ConversationHandler.END

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help message"""
    help_message = (
        "🤖 *Post Generator Bot Help*\n\n"
        "1. *Create New Post*: Start creating a new post with a thumbnail and video link.\n"
        "2. *Manage Channels*: Add or list channels where your posts will be shared.\n"
        "3. *Check Scheduled Posts*: View the status of your scheduled posts.\n"
        "4. *Help*: Get this help message.\n\n"
        "Use the buttons below to navigate through the bot's features."
    )

    keyboard = [
        [InlineKeyboardButton("🏠 Main Menu", callback_data='main_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.message.edit_text(help_message, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(help_message, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

    return ConversationHandler.END

async def add_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add a new channel"""
    message = update.message
    user_id = str(message.from_user.id)

    try:
        if hasattr(message, 'forward_from_chat') and message.forward_from_chat:
            channel_id = str(message.forward_from_chat.id)
        else:
            try:
                channel_id = str(int(message.text))
            except ValueError:
                await message.reply_text(
                    "⚠️ *Please send a valid channel ID or forward a message from the channel.*\n"
                    "Make sure the bot is an admin in the channel! 🤖",
                    parse_mode=ParseMode.MARKDOWN
                )
                return ADDING_CHANNEL

        try:
            chat = await context.bot.get_chat(channel_id)
            bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)

            if not bot_member.can_post_messages:
                await message.reply_text(
                    "⚠️ *I don't have permission to post messages in this channel.*\n"
                    "Please make sure I am an admin with posting rights! 🔑",
                    parse_mode=ParseMode.MARKDOWN
                )
                return ADDING_CHANNEL

        except Exception as e:
            logger.error(f"Error verifying channel access: {str(e)}")
            await message.reply_text(
                "❌ *I couldn't access this channel. Please make sure:*\n"
                "1. The channel ID is correct ✔️\n"
                "2. I am added as an admin in the channel 👑\n"
                "3. I have permission to post messages 📝",
                parse_mode=ParseMode.MARKDOWN
            )
            return ADDING_CHANNEL

        channels = load_channels()
        if user_id not in channels:
            channels[user_id] = []

        if channel_id not in channels[user_id]:
            channels[user_id].append(channel_id)
            save_channels(channels)
            await message.reply_text(
                f"✅ *Channel '{chat.title}' added successfully!* 🎉\n"
                "You can now create posts and they will be automatically shared to this channel.",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await message.reply_text("ℹ️ *This channel is already in your list!*", parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        logger.error(f"Error adding channel: {str(e)}")
        await message.reply_text(
            "❌ *There was an error adding the channel. Please make sure:*\n"
            "1. You provided a valid channel ID or forwarded message ✔️\n"
            "2. The bot is an admin in the channel 👑\n"
            "3. The channel exists and is accessible 🔍",
            parse_mode=ParseMode.MARKDOWN
        )

    keyboard = [
        [InlineKeyboardButton("➕ Add Another Channel", callback_data='add_channel')],
        [InlineKeyboardButton("📄 List Channels", callback_data='list_channels')],
        [InlineKeyboardButton("🏠 Main Menu", callback_data='main_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await message.reply_text(
        "*What would you like to do next?* 🤔",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

    return ConversationHandler.END

async def list_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all channels for the user"""
    if update.callback_query:
        user_id = str(update.callback_query.from_user.id)
        message = update.callback_query.message
    else:
        user_id = str(update.message.from_user.id)
        message = update.message

    channels = load_channels()
    if user_id in channels and channels[user_id]:
        channel_list = []
        for channel_id in channels[user_id]:
            try:
                chat = await context.bot.get_chat(channel_id)
                bot_member = await context.bot.get_chat_member(channel_id, context.bot.id)
                status = "✅ Active" if bot_member.can_post_messages else "⚠️ No Posting Permission"
                channel_list.append(
                    f"📺 *{chat.title}*\n"
                    f"   Channel ID: `{channel_id}`\n"
                    f"   Status: {status}"
                )
            except Exception:
                channel_list.append(
                    f"❌ *Inaccessible Channel*\n"
                    f"   Channel ID: `{channel_id}`\n"
                    f"   Status: Bot might have been removed"
                )

        message_text = (
            "📄 *Your Channels:*\n\n" +
            "\n\n".join(channel_list) +
            "\n\n✨ *To remove a channel:*\n" +
            "1. Use /start to restart\n" +
            "2. Choose 'Manage Channels'\n" +
            "3. Add only the channels you want to keep"
        )

        # Split message if it's too long
        if len(message_text) > 4096:
            chunks = [message_text[i:i+4096] for i in range(0, len(message_text), 4096)]
            for chunk in chunks:
                await message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)
        else:
            await message.reply_text(message_text, parse_mode=ParseMode.MARKDOWN)
    else:
        await message.reply_text(
            "📭 *You haven't added any channels yet!* 😞\n"
            "Use the 'Add Channel' option to add channels where you want your posts to appear. ➕",
            parse_mode=ParseMode.MARKDOWN
        )

    keyboard = [
        [InlineKeyboardButton("➕ Add Channel", callback_data='add_channel')],
        [InlineKeyboardButton("📝 Create New Post", callback_data='create_post')],
        [InlineKeyboardButton("🏠 Main Menu", callback_data='main_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await message.reply_text(
        "*What would you like to do next?* 🤔",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

    return ConversationHandler.END

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button clicks"""
    query = update.callback_query
    await query.answer()

    if query.data == 'create_post':
        await query.message.reply_text("🖼️ *Please send me a thumbnail (image, GIF, or video).*", parse_mode=ParseMode.MARKDOWN)
        return THUMBNAIL
    elif query.data == 'manage_channels':
        return await manage_channels(update, context)
    elif query.data == 'add_channel':
        await query.message.reply_text(
            "📢 *Please forward a message from the channel or send the channel ID.*\n"
            "Make sure the bot is an admin in the channel! 🤖",
            parse_mode=ParseMode.MARKDOWN
        )
        return ADDING_CHANNEL
    elif query.data == 'list_channels':
        return await list_channels(update, context)
    elif query.data == 'check_scheduled':
        return await check_scheduled_posts(update, context)
    elif query.data == 'help':
        return await help_command(update, context)
    elif query.data == 'cancel':
        return await cancel(update, context)
    elif query.data == 'main_menu':
        return await start(update, context)
    elif query.data in ['xrated', 'nightrider']:
        user_id = query.from_user.id
        user_data[user_id]['bot_type'] = query.data
        return await schedule_post_prompt(update, context)

    return ConversationHandler.END

async def manage_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show channel management options"""
    keyboard = [
        [InlineKeyboardButton("➕ Add Channel", callback_data='add_channel')],
        [InlineKeyboardButton("📄 List Channels", callback_data='list_channels')],
        [InlineKeyboardButton("📝 Create New Post", callback_data='create_post')],
        [InlineKeyboardButton("🏠 Main Menu", callback_data='main_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message = "📺 *Channel Management:*\n*What would you like to do?* 🤔"

    if update.callback_query:
        await update.callback_query.message.edit_text(message, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(message, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

    return ConversationHandler.END

async def thumbnail_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle received thumbnail and ask for video link"""
    message = update.message
    user_id = message.from_user.id

    if message.photo:
        file_id = message.photo[-1].file_id
        file_type = "photo"
    elif message.video:
        file_id = message.video.file_id
        file_type = "video"
    elif message.animation:
        file_id = message.animation.file_id
        file_type = "animation"
    else:
        await message.reply_text("⚠️ *Please send a valid thumbnail (photo, video, or GIF).*", parse_mode=ParseMode.MARKDOWN)
        return THUMBNAIL

    user_data[user_id] = {
        "thumbnail_id": file_id,
        "thumbnail_type": file_type
    }

    await message.reply_text("👍 *Great! Now please send me the video link.* 🔗", parse_mode=ParseMode.MARKDOWN)
    return VIDEO_LINK

async def video_link_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask the user to select the bot type"""
    user_id = update.message.from_user.id
    user_data[user_id]["video_link"] = escape_markdown(update.message.text)

    keyboard = [
        [InlineKeyboardButton("🔞 X-Rated Bot", callback_data='xrated')],
        [InlineKeyboardButton("🌙 Night Rider Bot", callback_data='nightrider')],
        [InlineKeyboardButton("🏠 Main Menu", callback_data='main_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "*Please select which bot you want to use for this post:* 🤖",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

    return BOT_SELECTION

async def schedule_post_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask whether to post now or schedule"""
    keyboard = [
        [InlineKeyboardButton("📤 Post Now", callback_data='post_now')],
        [InlineKeyboardButton("📅 Schedule", callback_data='schedule')],
        [InlineKeyboardButton("🏠 Main Menu", callback_data='main_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.message.edit_text(
        "*Would you like to post now or schedule the post?* ⏰",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

    return SCHEDULE_OR_POST_NOW

async def schedule_or_post_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle user's choice to post now or schedule"""
    query = update.callback_query
    await query.answer()

    if query.data == 'post_now':
        return await post_to_channels(update, context)
    elif query.data == 'schedule':
        await query.message.reply_text(
            "⏰ *Please provide the time to schedule the post (HH:MM format, IST).*\n"
            "Example: `14:30` for 2:30 PM",
            parse_mode=ParseMode.MARKDOWN
        )
        return SCHEDULE_TIME

async def post_to_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Post content immediately to all user's channels"""
    query = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    channels = load_channels()

    if user_id not in channels or not channels[user_id]:
        await query.message.reply_text(
            "❌ *You haven't added any channels yet!* 😞\n"
            "Please add channels first using the 'Manage Channels' option. 📺",
            parse_mode=ParseMode.MARKDOWN
        )
        return ConversationHandler.END

    success_channels = []
    failed_channels = []

    # Get tutorial link based on bot type
    tutorial_link = BOT_TUTORIALS[user_data[int(user_id)]['bot_type']]

    # Create the post text
    post_text = (
        f"{DECORATIVE_LINES[0]}\n\n"
        f"*🎬 VIDEO LINK:*\n"
        f"_{user_data[int(user_id)]['video_link']}_\n\n"
        f"{DECORATIVE_LINES[2]}\n\n"
        f"*📥 HOW TO DOWNLOAD AND WATCH VIDEO:*\n"
        f"_{escape_markdown(tutorial_link)}_\n\n"
        f"{DECORATIVE_LINES[3]}\n\n"
        f"*Made by \\- @Neonghost\\_Network* 🌟"
    )

    # Post to each channel
    for channel_id in channels[user_id]:
        try:
            if user_data[int(user_id)]["thumbnail_type"] == "photo":
                await context.bot.send_photo(
                    chat_id=channel_id,
                    photo=user_data[int(user_id)]["thumbnail_id"],
                    caption=post_text,
                    parse_mode=ParseMode.MARKDOWN_V2
                )
            elif user_data[int(user_id)]["thumbnail_type"] == "video":
                await context.bot.send_video(
                    chat_id=channel_id,
                    video=user_data[int(user_id)]["thumbnail_id"],
                    caption=post_text,
                    parse_mode=ParseMode.MARKDOWN_V2
                )
            elif user_data[int(user_id)]["thumbnail_type"] == "animation":
                await context.bot.send_animation(
                    chat_id=channel_id,
                    animation=user_data[int(user_id)]["thumbnail_id"],
                    caption=post_text,
                    parse_mode=ParseMode.MARKDOWN_V2
                )

            success_channels.append(channel_id)
            logger.info(f"Successfully posted to channel {channel_id}")

        except Exception as e:
            failed_channels.append(channel_id)
            logger.error(f"Failed to post to channel {channel_id}: {str(e)}")

    # Send status message
    status_message = "*📊 Post Status:*\n\n"
    if success_channels:
        status_message += "✅ *Successfully posted to:*\n"
        for channel_id in success_channels:
            status_message += f"- Channel ID: `{channel_id}`\n"
    if failed_channels:
        status_message += "\n❌ *Failed to post to:*\n"
        for channel_id in failed_channels:
            status_message += f"- Channel ID: `{channel_id}`\n"

    # Add buttons for next action
    keyboard = [
        [InlineKeyboardButton("📝 Create Another Post", callback_data='create_post')],
        [InlineKeyboardButton("🏠 Main Menu", callback_data='main_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.message.reply_text(status_message, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

    # Clear user data
    if int(user_id) in user_data:
        user_data.pop(int(user_id))

    return ConversationHandler.END

async def check_scheduled_posts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check the status of scheduled posts"""
    user_id = str(update.callback_query.from_user.id if update.callback_query else update.message.from_user.id)
    scheduled_posts = load_scheduled_posts().get(user_id, [])

    if not scheduled_posts:
        message = (
            "*📊 Scheduled Posts Status*\n\n"
            "🚫 *No posts scheduled at the moment!* 😞\n\n"
            "*Would you like to schedule a post?* 😊"
        )
    else:
        message = "*📊 Scheduled Posts Status*\n\n"
        now = datetime.now()

        # Filter and sort posts
        posted_posts = [
            post for post in scheduled_posts
            if datetime.strptime(post['time'], "%Y-%m-%d %H:%M:%S") < now and
            post.get('status', '').startswith('✅')
        ]
        pending_posts = [
            post for post in scheduled_posts
            if datetime.strptime(post['time'], "%Y-%m-%d %H:%M:%S") >= now
        ]

        # Show last 5 successful posts
        if posted_posts:
            message += "*Recently Posted:*\n"
            for post in sorted(posted_posts, key=lambda x: x['time'], reverse=True)[:5]:
                post_time = datetime.strptime(post['time'], "%Y-%m-%d %H:%M:%S")
                message += (
                    f"• {post['status']}\n"
                    f"  📅 {post_time.strftime('%Y-%m-%d %H:%M')} IST\n"
                )
            message += f"{'➖' * 15}\n"

        # Show all pending posts
        if pending_posts:
            message += "\n*Pending Posts:*\n"
            for post in sorted(pending_posts, key=lambda x: x['time']):
                post_time = datetime.strptime(post['time'], "%Y-%m-%d %H:%M:%S")
                message += (
                    f"• ⏳ Scheduled\n"
                    f"  📅 {post_time.strftime('%Y-%m-%d %H:%M')} IST\n"
                )

    keyboard = [
        [InlineKeyboardButton("📝 Schedule New Post", callback_data='create_post')],
        [InlineKeyboardButton("🏠 Main Menu", callback_data='main_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.message.edit_text(message, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(message, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

    return ConversationHandler.END

async def schedule_time_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Schedule the post at the specified time"""
    user_id = str(update.message.from_user.id)
    user_time = update.message.text

    try:
        # Parse the provided time in IST
        schedule_time = datetime.strptime(user_time, "%H:%M").time()
        now = datetime.now()
        schedule_datetime = datetime.combine(now, schedule_time)

        # If the scheduled time is in the past, schedule it for the next day
        if schedule_datetime < now:
            schedule_datetime += timedelta(days=1)

        # Load existing scheduled posts
        scheduled_posts = load_scheduled_posts()
        if user_id not in scheduled_posts:
            scheduled_posts[user_id] = []

        # Store channel information with the scheduled post
        channels = load_channels()
        user_channels = channels.get(user_id, [])

        # Get tutorial link based on bot type
        tutorial_link = BOT_TUTORIALS[user_data[int(user_id)]['bot_type']]

        # Create post data
        post_data = {
            "time": schedule_datetime.strftime("%Y-%m-%d %H:%M:%S"),
            "thumbnail_id": user_data[int(user_id)]["thumbnail_id"],
            "thumbnail_type": user_data[int(user_id)]["thumbnail_type"],
            "video_link": user_data[int(user_id)]["video_link"],
            "bot_type": user_data[int(user_id)]["bot_type"],
            "tutorial_link": tutorial_link,
            "status": "⏳ Pending",
            "channels": user_channels,
            "user_id": user_id
        }

        # Add new post to scheduled posts
        scheduled_posts[user_id].append(post_data)
        save_scheduled_posts(scheduled_posts)

        # Schedule the job
        scheduler.add_job(
            post_scheduled,
            'date',
            run_date=schedule_datetime,
            args=[context, post_data]
        )

        # Show success message
        await update.message.reply_text(
            f"✅ *Post successfully scheduled!* 🎉\n\n"
            f"📅 *Scheduled for:* {schedule_datetime.strftime('%Y-%m-%d')}\n"
            f"⏰ *Time:* {schedule_datetime.strftime('%H:%M')} IST",
            parse_mode=ParseMode.MARKDOWN
        )

        # Ask if user wants to schedule another post
        keyboard = [
            [InlineKeyboardButton("📝 Schedule Another Post", callback_data='create_post')],
            [InlineKeyboardButton("📊 View All Scheduled Posts", callback_data='check_scheduled')],
            [InlineKeyboardButton("🏠 Main Menu", callback_data='main_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "*Would you like to schedule another post?* 🤔",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )

        return CONFIRM_ANOTHER

    except ValueError:
        await update.message.reply_text(
            "⚠️ *Invalid time format!* 🕐\n"
            "Please provide the time in HH:MM format (e.g., `14:30`)",
            parse_mode=ParseMode.MARKDOWN
        )
        return SCHEDULE_TIME

async def post_scheduled(context: ContextTypes.DEFAULT_TYPE, post_data: dict):
    """Handle scheduled post execution"""
    try:
        success_channels = []
        failed_channels = []

        # Create the post text using the stored tutorial link
        post_text = (
            f"{DECORATIVE_LINES[0]}\n\n"
            f"*🎬 VIDEO LINK:*\n"
            f"_{post_data['video_link']}_\n\n"
            f"{DECORATIVE_LINES[2]}\n\n"
            f"*📥 HOW TO DOWNLOAD AND WATCH VIDEO:*\n"
            f"_{escape_markdown(post_data['tutorial_link'])}_\n\n"
            f"{DECORATIVE_LINES[3]}\n\n"
            f"*Made by \\- @Neonghost\\_Network* 🌟"
        )

        # Post to each channel
        for channel_id in post_data['channels']:
            try:
                if post_data["thumbnail_type"] == "photo":
                    await context.bot.send_photo(
                        chat_id=channel_id,
                        photo=post_data["thumbnail_id"],
                        caption=post_text,
                        parse_mode=ParseMode.MARKDOWN_V2
                    )
                elif post_data["thumbnail_type"] == "video":
                    await context.bot.send_video(
                        chat_id=channel_id,
                        video=post_data["thumbnail_id"],
                        caption=post_text,
                        parse_mode=ParseMode.MARKDOWN_V2
                    )
                elif post_data["thumbnail_type"] == "animation":
                    await context.bot.send_animation(
                        chat_id=channel_id,
                        animation=post_data["thumbnail_id"],
                        caption=post_text,
                        parse_mode=ParseMode.MARKDOWN_V2
                    )

                success_channels.append(channel_id)
                logger.info(f"Successfully posted scheduled post to channel {channel_id}")

            except Exception as e:
                failed_channels.append(channel_id)
                logger.error(f"Failed to post to channel {channel_id}: {str(e)}")

        # Update the post status
        scheduled_posts = load_scheduled_posts()
        user_id = post_data['user_id']
        if user_id in scheduled_posts:
            for post in scheduled_posts[user_id]:
                if post['time'] == post_data['time']:
                    post['status'] = f"✅ Posted ({len(success_channels)}/{len(post_data['channels'])} channels)"
            save_scheduled_posts(scheduled_posts)

        # Send status message to user
        if success_channels or failed_channels:
            status_message = "*📊 Scheduled Post Status Update:*\n\n"
            if success_channels:
                status_message += "✅ *Successfully posted to:*\n"
                for channel_id in success_channels:
                    status_message += f"- Channel ID: `{channel_id}`\n"
            if failed_channels:
                status_message += "\n❌ *Failed to post to:*\n"
                for channel_id in failed_channels:
                    status_message += f"- Channel ID: `{channel_id}`\n"

            try:
                await context.bot.send_message(
                    chat_id=int(user_id),
                    text=status_message,
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                logger.error(f"Failed to send status message to user: {str(e)}")

    except Exception as e:
        logger.error(f"Error in post_scheduled: {str(e)}")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the conversation"""
    user_id = update.effective_user.id

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.edit_text("❌ *Operation cancelled.* Send /start to begin again.", parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text("❌ *Operation cancelled.* Send /start to begin again.", parse_mode=ParseMode.MARKDOWN)

    if user_id in user_data:
        user_data.pop(user_id)

    return ConversationHandler.END

def main():
    """Start the bot"""
    # Replace with your bot token
    application = Application.builder().token('YOUR_BOT_TOKEN').build()

    # Add conversation handler
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
    )

    application.add_handler(conv_handler)

    # Start the scheduler
    scheduler.start()

    logger.info("✨ Bot is starting up...")
    print("🤖 Bot is running... Press Ctrl+C to stop.")

    application.run_polling()

if __name__ == '__main__':
    main()
