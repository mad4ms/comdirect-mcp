"""
Basic tour through the API: accounts, transactions, depots and documents.

Run from the repository root (needs the dev extras and a .env file, see .env.example):

    uv sync --all-extras
    uv run python examples/basic_example.py
"""

import os
from datetime import date, timedelta

from dotenv import load_dotenv

from comdirect_mcp.client import ComdirectClient
from comdirect_mcp.utils import (
    default_photo_tan_callback,
    default_push_tan_callback,
    default_sms_tan_callback,
)


def main():
    # Load environment variables from .env file
    # Ensure you have created a .env file based on .env.example
    load_dotenv()

    # Get credentials
    try:
        credentials = {
            "username": os.environ["COMDIRECT_USERNAME"],
            "password": os.environ["COMDIRECT_PASSWORD"],
            "client_id": os.environ["COMDIRECT_CLIENT_ID"],
            "client_secret": os.environ["COMDIRECT_CLIENT_SECRET"],
        }
    except KeyError as e:
        print(f"Error: Missing environment variable {e}")
        print("Please create a .env file in the root directory based on .env.example")
        return

    # Define callbacks for 2FA
    # You can use the defaults or provide authentication specific logic here
    tan_handlers = {
        "photo_tan_cb": default_photo_tan_callback,
        "sms_tan_cb": default_sms_tan_callback,
        "push_tan_cb": default_push_tan_callback,
    }

    # Initialize client
    print("Initializing client ...")
    client = ComdirectClient(credentials, tan_handlers)

    print("Logging in ...")
    try:
        client.login()
        print("Login successful.")
    except Exception as e:
        print(f"Login failed: {e}")
        return

    try:
        # Fetch account balances
        print("\nFetching Account Balances:")
        accounts = client.list_accounts()
        for account in accounts:
            print(f"- Account: {account.id}")
            print(f"  Balance: {account.balance} {account.currency}")
            print(f"  Available: {account.available}")

        # If there are accounts, fetch transactions for the first one
        if accounts:
            first_account_id = accounts[0].id
            print(f"\nFetching transactions for Account {first_account_id}:")
            today = date.today()
            transactions = client.list_transactions(
                first_account_id,
                min_booking_date=(today - timedelta(days=30)).isoformat(),
                max_booking_date=today.isoformat(),
            )
            if not transactions:
                print("No transactions found.")
            else:
                print(f"Found {len(transactions)} transactions in the last 30 days (first 5 are shown):")
            for tx in transactions[:5]:  # Show first 5
                print(f"- {tx.booking_date}: {tx.amount} {tx.currency} ({tx.type}) [Ref: {tx.reference or 'N/A'}]")
                if tx.remitter and tx.remitter.holder_name:
                    print(f"  Remitter: {tx.remitter.holder_name}")
                if tx.creditor and tx.creditor.holder_name:
                    print(f"  Creditor: {tx.creditor.holder_name}")
                if tx.purpose:
                    print(f"  Purpose: {tx.purpose}")

        # Fetch Depots
        print("\nFetching Depots:")
        depots = client.list_depots()
        for depot in depots:
            print(f"- Depot ID: {depot.id} (Display ID: {depot.display_id})")

            # Fetch positions
            print(f"  Fetching positions for depot {depot.id}...")
            balance, positions = client.get_depot_positions(depot.id)
            print(f"  Depot Value: {balance.current_value} {balance.current_value_currency}")
            for pos in positions[:5]:
                name = pos.instrument_name or pos.wkn
                value = f"{pos.current_value} {pos.current_value_currency}"
                print(f"  - {name} ({pos.isin}): {pos.quantity} {pos.quantity_unit}, {value}")

        # Fetch Documents
        print("\nFetching Documents:")
        documents = client.list_documents()
        for doc in documents:
            print(f"- Document ID: {doc.id}, Name: {doc.name}, Date: {doc.date_creation}")
            # Download document content (first 1 for demo)
            content = client.download_document(doc.id, mime_type=doc.mime_type)
            print(f"  Downloaded {len(content)} bytes.")
            break  # Only download first document for demo
    except Exception as e:
        print(f"An error occurred during data fetching: {e}")

    finally:
        print("\nLogging out...")
        client.logout()
        print("Logged out.")


if __name__ == "__main__":
    main()
