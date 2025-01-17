from typing import Dict

# Conversation states
NAME, LOCATION, PRODUCT_SELECTION, QUANTITY = range(4)

# Emojis for various UI elements
EMOJIS: Dict[str, str] = {
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

# Building emojis for locations
BUILDINGS: Dict[str, str] = {
    '4Seasons': '🏢',
    'Omega': '🏬',
    'Kamanina': '🏘️',
    'Genuez': '🏡'
} 