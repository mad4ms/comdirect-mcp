"""Allowlisted diagnostics for live checks; never reproduce error bodies or values."""

import re
from collections.abc import Iterable


def tool_error_diagnostic(messages: Iterable[str]) -> str:
    for message in messages:
        status = re.search(r"comdirect API error: HTTP ([1-5]\d{2})\b", message)
        if status:
            return "api_http_" + status.group(1)
        for marker, category in (
            ("Bank returned an incomplete depot transaction list", "incomplete_depot_list"),
            ("Depot transaction has no booking date", "missing_booking_date"),
            ("Instrument lookup did not return exactly one match", "ambiguous_instrument"),
            ("Order dimensions did not return exactly one match", "ambiguous_order_dimensions"),
            ("Position lookup did not return exactly one match", "ambiguous_position"),
            ("Bank returned an incomplete position list", "incomplete_positions"),
            ("Bank returned an incomplete order list", "incomplete_orders"),
            ("Order count changed while paging", "unstable_orders"),
            ("PDF text could not be extracted", "pdf_extraction_failed"),
            ("Portfolio contains missing values/currencies", "incomplete_portfolio_values"),
            ("Invalid isoformat string", "invalid_date_format"),
            ("ConversionSyntax", "invalid_decimal_format"),
            ("Network error contacting comdirect", "authentication_network_error"),
            ("Missing credentials:", "missing_credentials"),
            ("TAN challenges were started without a confirmed TAN", "challenge_limit"),
        ):
            if marker in message:
                return category
        for stage in (
            "Primary OAuth",
            "Session creation",
            "Session validation init",
            "TAN confirmation",
            "Secondary OAuth",
        ):
            status = re.search(re.escape(stage) + r" failed \(HTTP ([1-5]\d{2})\)", message)
            if status:
                return stage.lower().replace(" ", "_") + "_http_" + status.group(1)
    return "unclassified_tool_error"
