from telegram import Update
from telegram.ext import ConversationHandler
from ..utils.constants import AUTHORIZED_USERS_IDS, AUTHORIZED_USERS_USERNAMES

async def check_auth(update: Update) -> bool:
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    if user_id in AUTHORIZED_USERS_IDS:
        return True
    
    if username and f"@{username.lower()}" in AUTHORIZED_USERS_USERNAMES:
        return True
        
    await update.message.reply_text("Sorry, you are not authorized to use this bot.")
    return False 