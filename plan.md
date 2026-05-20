1. **Apply code fix via `replace_with_git_merge_diff`**: I will update `_call_get_member_objects` in `src/auth_graph.py` using `replace_with_git_merge_diff`. I will add a check `if next_url == "None": break` right after `if not next_url: break`. The prompt says "while url and url != 'None':" so the issue is that it should check if `next_url == "None"`.
2. **Add Tests via `replace_with_git_merge_diff`**: I will use `replace_with_git_merge_diff` to add specific test cases to `tests/test_auth_graph.py` to ensure that a server returning the literal string `"None"` as `nextLink` successfully terminates the pagination.
3. **Run the full test suite**: I will use `run_in_bash_session` to execute `python -m pytest` and ensure that all existing and new tests pass successfully.
4. **Complete pre-commit steps to ensure proper testing, verification, review, and reflection are done.**
5. **Submit PR**: I will call `request_code_review` to finalize the process.
