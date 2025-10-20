import random
from datetime import datetime, timedelta
import uuid
import json

PROJECT_ID = "just-episode-473505-h7"  # Replace with your actual GCP project ID
DATASET_ID = "ecommerce_analytics"
REGION = "US"

# --- Main Script ---


def create_dataset_and_tables():
    """
    Orchestrates the creation of the dataset, tables, and data insertion.
    """
    from google.cloud import bigquery
    client = bigquery.Client(project=PROJECT_ID)

    try:
        print(f"1. Creating or checking for dataset '{PROJECT_ID}.{DATASET_ID}' in region '{REGION}'...")
        dataset_ref = bigquery.DatasetReference(PROJECT_ID, DATASET_ID)
        dataset = bigquery.Dataset(dataset_ref)
        dataset.location = REGION
        client.create_dataset(dataset, exists_ok=True)
        print("Dataset created or already exists.")

        # --- Define Schemas and Data Generation Functions ---

        customer_schema = [
            bigquery.SchemaField("customer_id", "STRING", mode="REQUIRED", description="Unique identifier for the customer."),
            bigquery.SchemaField("first_name", "STRING", mode="REQUIRED", description="Customer's first name."),
            bigquery.SchemaField("last_name", "STRING", mode="REQUIRED", description="Customer's last name."),
            bigquery.SchemaField("email", "STRING", mode="REQUIRED", description="Customer's email address."),
            bigquery.SchemaField("signup_date", "DATE", mode="REQUIRED", description="Date the customer signed up."),
            bigquery.SchemaField("member_since", "TIMESTAMP", mode="REQUIRED", description="Timestamp when the customer record was created in the system, often different from signup date."),
            bigquery.SchemaField("last_login_date", "DATE", mode="NULLABLE", description="Date of the customer's last login."),
        ]

        def generate_customer_data(num_rows=100):
            customers = []
            for _ in range(num_rows):
                first = random.choice(["Alice", "Bob", "Charlie", "Diana", "Eve", "Frank", "Grace"])
                last = random.choice(["Smith", "Jones", "Williams", "Brown", "Davis", "Miller"])
                customer_id = str(uuid.uuid4())
                signup_date = (datetime.now() - timedelta(days=random.randint(100, 500))).date()
                last_login_date = signup_date + timedelta(days=random.randint(0, 90))
                member_since = datetime.now() - timedelta(days=random.randint(1, 600))
                customers.append({
                    "customer_id": customer_id,
                    "first_name": first,
                    "last_name": last,
                    "email": f"{first.lower()}{last.lower()}{random.randint(10, 99)}@example.com",
                    "signup_date": signup_date.strftime("%Y-%m-%d"),
                    "member_since": member_since.isoformat(),
                    "last_login_date": last_login_date.strftime("%Y-%m-%d")
                })
            return customers

        product_category_schema = [
            bigquery.SchemaField("category_id", "STRING", mode="REQUIRED", description="Unique identifier for the product category."),
            bigquery.SchemaField("category_name", "STRING", mode="REQUIRED", description="Name of the product category."),
        ]

        def generate_product_category_data():
            categories = ["Electronics", "Clothing", "Home Goods", "Books", "Toys"]
            return [
                {"category_id": str(uuid.uuid4()), "category_name": name}
                for name in categories
            ]

        product_schema = [
            bigquery.SchemaField("product_id", "STRING", mode="REQUIRED", description="Unique identifier for the product."),
            bigquery.SchemaField("product_name", "STRING", mode="REQUIRED", description="Name of the product."),
            bigquery.SchemaField("prod_cat_id", "STRING", mode="REQUIRED", description="Foreign key to the product_category table."),
            bigquery.SchemaField("price_usd", "FLOAT", mode="REQUIRED", description="Price of the product in USD."),
            bigquery.SchemaField("created_at_ts", "TIMESTAMP", mode="REQUIRED", description="Timestamp when the product was added to the catalog."),
            bigquery.SchemaField("catalog_effective_date", "DATE", mode="REQUIRED", description="Date the product became visible in the online catalog."),
            bigquery.SchemaField("last_updated_at_ts", "TIMESTAMP", mode="REQUIRED", description="Timestamp when the product details were last updated."),
            bigquery.SchemaField("is_available", "BOOLEAN", mode="REQUIRED", description="Availability status of the product."),
        ]

        def generate_product_data(categories, num_rows=50):
            products = []
            for _ in range(num_rows):
                product_id = str(uuid.uuid4())
                category = random.choice(categories)
                product_name = f"{category['category_name']} Item {random.randint(1, 100)}"
                price = round(random.uniform(10.0, 500.0), 2)
                created_at = datetime.now() - timedelta(days=random.randint(5, 150))
                last_updated_at = created_at + timedelta(days=random.randint(0, 10))
                catalog_effective_date = created_at.date() + timedelta(days=random.randint(0, 5))
                products.append({
                    "product_id": product_id,
                    "product_name": product_name,
                    "prod_cat_id": category['category_id'],
                    "price_usd": price,
                    "created_at_ts": created_at.isoformat(),
                    "catalog_effective_date": catalog_effective_date.strftime("%Y-%m-%d"),
                    "last_updated_at_ts": last_updated_at.isoformat(),
                    "is_available": random.choice([True, True, True, False])
                })
            return products

        order_schema = [
            bigquery.SchemaField("order_id", "STRING", mode="REQUIRED", description="Unique identifier for the order."),
            bigquery.SchemaField("cust_acct_id", "STRING", mode="REQUIRED", description="Foreign key to the customer table, but with a non-standard name."),
            bigquery.SchemaField("order_total_usd", "FLOAT", mode="REQUIRED", description="Total price of the order."),
            bigquery.SchemaField("order_date", "DATE", mode="REQUIRED"),
            bigquery.SchemaField("order_date_1", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("order_date_2", "TIMESTAMP", mode="REQUIRED"),
            bigquery.SchemaField("shipping_date", "DATE", mode="REQUIRED", description="The date the order was shipped. Should be after order_date."),
            bigquery.SchemaField("delivery_date", "DATE", mode="NULLABLE", description="The date the order was delivered. Should be after shipping_date."),
            bigquery.SchemaField("payment_method", "STRING", mode="REQUIRED", description="Payment method used for the order."),
        ]

        def generate_order_data(customers, num_rows=100):
            orders = []
            for _ in range(num_rows):
                customer = random.choice(customers)
                order_date = datetime.now() - timedelta(days=random.randint(1, 90))
                order_date_1 = order_date.strftime("%m/%d/%Y") # Incorrect format for BigQuery DATE type
                order_date_2 = order_date + timedelta(minutes=random.randint(1, 60))
                shipping_date = order_date + timedelta(days=random.randint(1, 5))
                delivery_date = shipping_date + timedelta(days=random.randint(1, 10)) if random.random() > 0.1 else None
                orders.append({
                    "order_id": str(uuid.uuid4()),
                    "cust_acct_id": customer["customer_id"],
                    "order_total_usd": 0.0,  # Placeholder, will be updated by generate_order_item_data
                    "order_date": order_date.strftime("%Y-%m-%d"),
                    "order_date_1": order_date_1,
                    "order_date_2": order_date_2.isoformat(),
                    "shipping_date": shipping_date.strftime("%Y-%m-%d"),
                    "delivery_date": delivery_date.strftime("%Y-%m-%d") if delivery_date else None,
                    "payment_method": random.choice(["Credit Card", "PayPal", "Apple Pay"]),
                })
            return orders

        order_item_schema = [
            bigquery.SchemaField("order_item_id", "STRING", mode="REQUIRED", description="Unique identifier for the order item."),
            bigquery.SchemaField("order_num", "STRING", mode="REQUIRED", description="Foreign key to the orders table, but with a non-standard name."),
            bigquery.SchemaField("item_id", "STRING", mode="REQUIRED", description="Foreign key to the products table, but with a non-standard name."),
            bigquery.SchemaField("quantity", "INTEGER", mode="REQUIRED", description="Number of units of the product in this order item."),
            bigquery.SchemaField("line_item_total", "FLOAT", mode="REQUIRED", description="Price of the single line item (quantity * price)."),
        ]

        def generate_order_item_data(orders, products):
            order_items = []
            order_totals = {order['order_id']: 0.0 for order in orders}

            for order in orders:
                num_items = random.randint(1, 3)
                for _ in range(num_items):
                    product = random.choice(products)
                    quantity = random.randint(1, 5)
                    line_item_total = quantity * product['price_usd']

                    order_items.append({
                        "order_item_id": str(uuid.uuid4()),
                        "order_num": order["order_id"],
                        "item_id": product["product_id"],
                        "quantity": quantity,
                        "line_item_total": round(line_item_total, 2)
                    })
                    order_totals[order['order_id']] += line_item_total

            # Update the order_total_usd in the orders data
            for order in orders:
                order['order_total_usd'] = round(order_totals[order['order_id']], 2)

            return order_items


        # --- Generate Data ---
        print("2. Generating sample data...")
        customers_data = generate_customer_data()
        categories_data = generate_product_category_data()
        products_data = generate_product_data(categories_data)
        orders_data = generate_order_data(customers_data)
        order_items_data = generate_order_item_data(orders_data, products_data)
        print("Sample data generated successfully.")

        # --- Create Tables and Insert Data ---
        table_definitions = {
            "customers": {"schema": customer_schema, "data": customers_data},
            "product_category": {"schema": product_category_schema, "data": categories_data},
            "products": {"schema": product_schema, "data": products_data},
            "orders": {"schema": order_schema, "data": orders_data},
            "order_item": {"schema": order_item_schema, "data": order_items_data},
        }

        for table_id, definition in table_definitions.items():
            print(f"\n3. Creating table '{table_id}' and loading data...")
            table_ref = dataset_ref.table(table_id)
            job_config = bigquery.LoadJobConfig(schema=definition["schema"])
            job_config.write_disposition = bigquery.WriteDisposition.WRITE_TRUNCATE

            job = client.load_table_from_json(
                definition["data"], table_ref, job_config=job_config
            )
            job.result()
            print(f"Table '{table_id}' created and data loaded successfully. Total rows: {job.output_rows}")

        print("\nAll tables created and populated successfully!")
        print(f"You can now query your data in BigQuery at: {PROJECT_ID}.{DATASET_ID}")

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    create_dataset_and_tables()