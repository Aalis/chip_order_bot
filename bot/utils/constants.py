import os

# Conversation states
NAME, LOCATION, PRODUCT_SELECTION, QUANTITY = range(4)

# Emojis for UI elements
EMOJIS = {
    'CART': '🛒',
    'MONEY': '💰',
    'PRODUCT': '💠',
    'CONFIRM': '✅',
    'WARNING': '⚠️',
    'ERROR': '❌',
    'PERSON': '👤',
    'LOCATION': '📍',
    'SHOPPING': '🛍️',
    'PACKAGE': '📦',
    'ARROW': '🔽',
    'WAVE': '👋',
    'PLUS': '➕',
    'STATS': '📊'
}

# Building locations with emojis
BUILDINGS = {
    '4Seasons': '🏢',
    'Omega': '🏬',
    'Kamanina': '🏘️',
    'Genuez': '🏡'
}

# Initialize authorized users from environment variables
AUTHORIZED_USERS_IDS = set()
AUTHORIZED_USERS_USERNAMES = set()

for user in os.getenv('AUTHORIZED_USERS', '').split(','):
    user = user.strip()
    if user.startswith('@'):
        AUTHORIZED_USERS_USERNAMES.add(user.lower())
    elif user.isdigit():
        AUTHORIZED_USERS_IDS.add(int(user)) 