"""A pytest-free smoke check for the refund agent.

Imports agent.py's lookup_order and get_order_status (never issue_refund, never the
model) and checks that orders.json loads, every order has the six expected fields, every
currency is a three-letter code and every amount is positive. Also re-reads orders.json
raw, since a dict built from it would silently drop a duplicate order_id key.

    uv run python smoke.py
"""

import json
import sys

from agent import HERE, ORDERS, get_order_status, lookup_order

EXPECTED_FIELDS = {"order_id", "owner", "amount", "currency", "status", "placed_on"}


def check_raw_orders_json() -> list[str]:
    failures = []

    def hook(pairs):
        seen = set()
        for key, _ in pairs:
            if key in seen:
                failures.append(f"order_id {key!r} appears more than once in orders.json")
            seen.add(key)
        return dict(pairs)

    raw_orders = json.loads((HERE / "orders.json").read_text(), object_pairs_hook=hook)
    for key, order in raw_orders.items():
        if order.get("order_id") != key:
            failures.append(
                f"order {key!r}: orders.json key does not match its order_id field {order.get('order_id')!r}"
            )
    return failures


def main() -> int:
    if not ORDERS:
        print("FAIL: orders.json loaded no orders", file=sys.stderr)
        return 1

    failures = check_raw_orders_json()
    for order_id, order in ORDERS.items():
        missing = EXPECTED_FIELDS - order.keys()
        if missing:
            failures.append(f"order {order_id} is missing fields: {sorted(missing)}")
            continue
        looked_up = lookup_order(order_id)
        if looked_up != order:
            failures.append(f"order {order_id}: lookup_order returned a different record")
        status = get_order_status(order_id)
        if status["order_id"] != order["order_id"] or status["status"] != order["status"]:
            failures.append(f"order {order_id}: get_order_status disagrees with orders.json")
        currency = order["currency"]
        if not (isinstance(currency, str) and len(currency) == 3 and currency.isalpha()):
            failures.append(f"order {order_id}: currency {currency!r} is not a three-letter code")
        amount = order["amount"]
        if not amount > 0:
            failures.append(f"order {order_id}: amount {amount!r} is not positive")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1

    print(f"smoke: {len(ORDERS)} orders ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
