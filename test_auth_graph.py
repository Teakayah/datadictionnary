import src.auth_graph as ag
from unittest.mock import patch, MagicMock

@patch('requests.get')
@patch('requests.post')
def test_call_get_member_objects_infinite_loop(mock_post, mock_get):
    mock_post_resp = MagicMock()
    mock_post_resp.json.return_value = {
        "value": ["group1"],
        "@odata.nextLink": "url1"
    }
    mock_post.return_value = mock_post_resp

    mock_get_resp = MagicMock()
    # The current code:
    # seen_urls.add(next_url)
    # resp = requests.get(next_url)
    # This means the loop will detect duplicate `next_url` ONLY if the server returns the EXACT SAME `next_url`.
    # What if the server returns a different `next_url`, but that `next_url` just redirects back to an earlier one?
    # Or what if we just strip query params and realize they are dupes?

    pass
