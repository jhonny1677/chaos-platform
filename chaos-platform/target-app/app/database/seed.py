import logging
from sqlalchemy import select, func
from app.database.connection import AsyncSessionLocal, ProductDB, UserDB

logger = logging.getLogger("target-app")

# 20 realistic fake products covering several categories
PRODUCTS = [
    {"name": "Wireless Keyboard", "price": 79.99, "stock": 150, "category": "Electronics", "description": "Compact wireless keyboard with 12-month battery life"},
    {"name": "USB-C Hub 7-in-1", "price": 49.99, "stock": 200, "category": "Electronics", "description": "HDMI, 3x USB-A, SD card, 100W PD passthrough"},
    {"name": "Mechanical Mouse", "price": 59.99, "stock": 120, "category": "Electronics", "description": "Precision gaming mouse with adjustable 100–16000 DPI"},
    {"name": "27-inch QHD Monitor", "price": 349.99, "stock": 45, "category": "Electronics", "description": "IPS panel, 144Hz, 1ms, HDR400"},
    {"name": "Laptop Stand Aluminium", "price": 39.99, "stock": 300, "category": "Accessories", "description": "Adjustable height, foldable, supports up to 17 inch"},
    {"name": "LED Desk Lamp", "price": 29.99, "stock": 250, "category": "Home Office", "description": "5 colour modes, USB-A charging port, memory function"},
    {"name": "1080p Webcam", "price": 89.99, "stock": 75, "category": "Electronics", "description": "Auto-focus, built-in stereo microphone, privacy shutter"},
    {"name": "ANC Headphones", "price": 199.99, "stock": 60, "category": "Audio", "description": "Over-ear, 30h battery, hybrid active noise cancelling"},
    {"name": "Smartwatch Series 5", "price": 249.99, "stock": 40, "category": "Wearables", "description": "GPS, heart rate, SpO2, 7-day battery"},
    {"name": "Portable SSD 1TB", "price": 119.99, "stock": 90, "category": "Storage", "description": "USB-C, 1050 MB/s read, IP55 water resistant"},
    {"name": "Mechanical Keyboard TKL", "price": 149.99, "stock": 80, "category": "Electronics", "description": "Hot-swap, Cherry MX Red switches, per-key RGB"},
    {"name": "Cable Management Kit", "price": 19.99, "stock": 500, "category": "Accessories", "description": "50 velcro ties, 20 cable clips, 10 cable sleeves"},
    {"name": "Ergonomic Chair", "price": 449.99, "stock": 25, "category": "Furniture", "description": "Lumbar support, adjustable armrests, breathable mesh"},
    {"name": "Large Desk Mat", "price": 24.99, "stock": 400, "category": "Accessories", "description": "90x40cm, anti-slip base, waterproof surface"},
    {"name": "Power Bank 20000mAh", "price": 49.99, "stock": 180, "category": "Electronics", "description": "65W USB-C PD, charges laptop, dual output"},
    {"name": "Raspberry Pi 4 4GB", "price": 79.99, "stock": 35, "category": "Electronics", "description": "Quad-core 1.8GHz, 4GB RAM, dual HDMI 4K"},
    {"name": "USB Condenser Microphone", "price": 99.99, "stock": 65, "category": "Audio", "description": "Cardioid pattern, 192kHz/24-bit, plug-and-play"},
    {"name": "Drawing Tablet 10x6", "price": 179.99, "stock": 30, "category": "Electronics", "description": "8192 levels pressure, battery-free stylus, 8 express keys"},
    {"name": "HDMI 2.1 Cable 2m", "price": 14.99, "stock": 600, "category": "Cables", "description": "48Gbps, 8K@60Hz, 4K@120Hz, eARC"},
    {"name": "8-Outlet Surge Protector", "price": 34.99, "stock": 220, "category": "Power", "description": "4320J rating, 4 USB ports, 2m cord"},
]

# 10 fake users
USERS = [
    {"name": "Alice Johnson", "email": "alice@example.com", "address": "123 Main St, San Francisco, CA 94105"},
    {"name": "Bob Smith", "email": "bob@example.com", "address": "456 Oak Ave, New York, NY 10001"},
    {"name": "Carol Williams", "email": "carol@example.com", "address": "789 Pine Rd, Austin, TX 73301"},
    {"name": "David Brown", "email": "david@example.com", "address": "321 Elm St, Seattle, WA 98101"},
    {"name": "Eva Martinez", "email": "eva@example.com", "address": "654 Maple Dr, Chicago, IL 60601"},
    {"name": "Frank Davis", "email": "frank@example.com", "address": "987 Cedar Ln, Boston, MA 02101"},
    {"name": "Grace Wilson", "email": "grace@example.com", "address": "147 Birch Blvd, Denver, CO 80201"},
    {"name": "Henry Taylor", "email": "henry@example.com", "address": "258 Walnut St, Portland, OR 97201"},
    {"name": "Iris Anderson", "email": "iris@example.com", "address": "369 Spruce Ave, Miami, FL 33101"},
    {"name": "Jack Thomas", "email": "jack@example.com", "address": "741 Ash Ct, Los Angeles, CA 90001"},
]


async def seed_database() -> None:
    """Idempotent seed — inserts data only when the products table is empty."""
    async with AsyncSessionLocal() as session:
        count = await session.scalar(select(func.count()).select_from(ProductDB))
        if count and count > 0:
            logger.info("Database already seeded (%d products), skipping", count)
            return

        for p in PRODUCTS:
            session.add(ProductDB(**p))

        for u in USERS:
            session.add(UserDB(**u))

        await session.commit()
        logger.info("Seeded %d products and %d users", len(PRODUCTS), len(USERS))
