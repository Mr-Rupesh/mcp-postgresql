import os
import random
from datetime import date, timedelta

import psycopg2
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://mcp:mcptest@localhost:5432/ecommerce"
)

SCHEMA_SQL = """
DROP TABLE IF EXISTS order_items CASCADE;
DROP TABLE IF EXISTS orders CASCADE;
DROP TABLE IF EXISTS products CASCADE;
DROP TABLE IF EXISTS customers CASCADE;

CREATE TABLE customers (
    customer_id SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    email       VARCHAR(150) UNIQUE NOT NULL,
    city        VARCHAR(50),
    signup_date DATE NOT NULL
);

CREATE TABLE products (
    product_id SERIAL PRIMARY KEY,
    name       VARCHAR(150) NOT NULL,
    category   VARCHAR(50)  NOT NULL,
    price      NUMERIC(10,2) NOT NULL CHECK (price > 0),
    stock      INT NOT NULL DEFAULT 0 CHECK (stock >= 0)
);

CREATE TABLE orders (
    order_id     SERIAL PRIMARY KEY,
    customer_id  INT  NOT NULL REFERENCES customers(customer_id),
    order_date   DATE NOT NULL,
    status       VARCHAR(20) NOT NULL
                 CHECK (status IN ('pending','shipped','delivered','cancelled'))
);

CREATE TABLE order_items (
    order_item_id SERIAL PRIMARY KEY,
    order_id      INT NOT NULL REFERENCES orders(order_id),
    product_id    INT NOT NULL REFERENCES products(product_id),
    quantity      INT NOT NULL CHECK (quantity > 0),
    unit_price    NUMERIC(10,2) NOT NULL
);

CREATE INDEX idx_orders_customer ON orders(customer_id);
CREATE INDEX idx_orders_date    ON orders(order_date);
CREATE INDEX idx_order_items_order   ON order_items(order_id);
CREATE INDEX idx_order_items_product ON order_items(product_id);
"""

FIRST = ["Ava","Liam","Maya","Noah","Zoe","Ethan","Ivy","Omar","Lena","Kai",
         "Nina","Ravi","Tara","Leo","Mira","Hugo","Anya","Felix","Sara","Dante"]
LAST  = ["Sharma","Chen","Patel","Kim","Garcia","Muller","Rossi","Novak","Silva","Okafor",
         "Tanaka","Dubois","Haddad","Ivanov","Costa","Weber","Larsen","Moreau","Petrov","Reyes"]
CITIES = ["New York","San Francisco","Austin","Seattle","Chicago","Denver",
          "Boston","Portland","Miami","Atlanta"]
CATEGORIES = {
    "Electronics": ["Wireless Mouse","Mechanical Keyboard","USB-C Hub","Webcam 1080p",
                    "Noise-Cancelling Headphones","Portable SSD 1TB","Smart Speaker","Power Bank 20k"],
    "Home & Kitchen": ["French Press","Cast Iron Skillet","Bamboo Cutting Board",
                       "Stand Mixer","Air Fryer","Robot Vacuum"],
    "Books": ["The Pragmatic Programmer","Designing Data-Intensive Applications",
              "Clean Code","Deep Learning","Sapiens","Atomic Habits"],
    "Fitness": ["Yoga Mat","Adjustable Dumbbell Set","Resistance Bands","Foam Roller"],
    "Apparel": ["Merino Wool Hoodie","Trail Running Shoes","Canvas Backpack","Denim Jacket"],
    "Garden": ["Raised Garden Bed Kit","LED Grow Light","Compost Bin","Pruning Shears"],
}
STATUSES = ["delivered"] * 70 + ["shipped"] * 15 + ["pending"] * 8 + ["cancelled"] * 7


def seed(cur) -> None:
    rng = random.Random(42) 

    # customers
    customers = []
    used_emails = set()
    for i in range(60):
        name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        email = f"{name.split()[0].lower()}.{name.split()[1].lower()}{i}@example.com"
        if email in used_emails:
            continue
        used_emails.add(email)
        signup = date.today() - timedelta(days=rng.randint(30, 720))
        customers.append((name, email, rng.choice(CITIES), signup))
    cur.executemany(
        "INSERT INTO customers (name, email, city, signup_date) VALUES (%s,%s,%s,%s)",
        customers,
    )

    # products
    products = []
    for category, names in CATEGORIES.items():
        base = {"Electronics": (25, 400), "Home & Kitchen": (15, 250),
                "Books": (10, 60), "Fitness": (10, 150),
                "Apparel": (20, 180), "Garden": (12, 200)}[category]
        for name in names:
            price = round(rng.uniform(*base), 2)
            products.append((name, category, price, rng.randint(0, 120)))
    cur.executemany(
        "INSERT INTO products (name, category, price, stock) VALUES (%s,%s,%s,%s)",
        products,
    )

    # orders + order_items (last 12 months)
    today = date.today()
    n_customers = len(customers)
    n_products = len(products)
    for _ in range(200):
        customer_id = rng.randint(1, n_customers)
        order_date = today - timedelta(days=rng.randint(0, 365))
        status = rng.choice(STATUSES)
        cur.execute(
            "INSERT INTO orders (customer_id, order_date, status) VALUES (%s,%s,%s) RETURNING order_id",
            (customer_id, order_date, status),
        )
        order_id = cur.fetchone()[0]
        items = []
        for product_id in rng.sample(range(1, n_products + 1), rng.randint(1, 4)):
            cur.execute("SELECT price FROM products WHERE product_id=%s", (product_id,))
            unit_price = float(cur.fetchone()[0])
            items.append((order_id, product_id, rng.randint(1, 3), unit_price))
        cur.executemany(
            "INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES (%s,%s,%s,%s)",
            items,
        )


def main() -> None:
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
            seed(cur)
        conn.commit()
        print("✅ Schema created and data seeded.")
        with conn.cursor() as cur:
            for table in ("customers", "products", "orders", "order_items"):
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                print(f"   {table:12s}: {cur.fetchone()[0]} rows")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()