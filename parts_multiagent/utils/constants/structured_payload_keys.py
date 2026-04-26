"""Keys for structured DataPart payloads.

This project avoids hard-coded dict keys in code. Import these constants
whenever you access or build structured payload dictionaries.
"""

PATH = 'path'
PAYLOAD = 'payload'

QUERY = 'query'

AGENT_NAME = 'agent_name'
TARGET_AGENT = 'target_agent'
SUPPLIER_AGENT = 'supplier_agent'
ITEMS = 'items'
PART = 'part'
QUANTITY = 'quantity'

RAW_ITEMS = 'raw_items'
RAW_QUERY = 'raw_query'
ORDER_CANDIDATES = 'order_candidates'
SUMMARY_MESSAGE = 'summary_message'
CONFIRMATION_PROMPT = 'confirmation_prompt'
ESTIMATED_DELIVERY_TIME = 'estimated_delivery_time'
TOTAL_PRICE = 'total_price'
PAYMENT_URL = 'payment_url'
ORDER_ID = 'order_id'
