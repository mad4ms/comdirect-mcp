from comdirect_mcp._diagnostics import tool_error_diagnostic


def test_http_diagnostic_never_copies_body_reason_or_identifiers():
    assert (
        tool_error_diagnostic(["comdirect API error: HTTP 422 SECRET reason; account=private-id; amount=123.45"])
        == "api_http_422"
    )
    assert tool_error_diagnostic(["SECRET credentials and unrecognized bank response"]) == "unclassified_tool_error"


def test_diagnostic_distinguishes_transport_mapping_and_login_stages():
    assert (
        tool_error_diagnostic(["Bank returned an incomplete depot transaction list. private details"])
        == "incomplete_depot_list"
    )
    assert tool_error_diagnostic(["Invalid isoformat string: 'private value'"]) == "invalid_date_format"
    assert tool_error_diagnostic(["TAN confirmation failed (HTTP 400) sensitive body"]) == "tan_confirmation_http_400"
