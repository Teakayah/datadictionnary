import time
import uuid

# Mock streamlit with a heavy get
class SessionState(dict):
    def get(self, key, default=None):
        # simulate heavy overhead for Streamlit's session_state proxy
        time.sleep(0.001)
        return super().get(key, default)

class St:
    pass
st = St()
st.session_state = SessionState()

def setup_data(num_objects: int, comments_per_object: int):
    demo_comments = {}
    target_id = None
    for i in range(num_objects):
        obj_name = f"obj_{i}"
        comments = []
        for j in range(comments_per_object):
            cid = str(uuid.uuid4())
            if i == num_objects - 1 and j == comments_per_object - 1:
                target_id = cid
            comments.append({
                "comment_id": cid,
                "author_email": f"author_{i}_{j}@example.com"
            })
        demo_comments[obj_name] = comments
    st.session_state["demo_comments"] = demo_comments
    return target_id

def bench_original(target_id: str, iterations: int):
    start = time.perf_counter()
    for _ in range(iterations):
        for comments in st.session_state.get("demo_comments", {}).values():
            for c in comments:
                if c.get("comment_id") == target_id:
                    res = str(c.get("author_email") or "")
                    break
    end = time.perf_counter()
    return end - start

def bench_optimized(target_id: str, iterations: int):
    start = time.perf_counter()
    for _ in range(iterations):
        demo_comments = st.session_state.get("demo_comments", {})
        for comments in demo_comments.values():
            for c in comments:
                if c.get("comment_id") == target_id:
                    res = str(c.get("author_email") or "")
                    break
    end = time.perf_counter()
    return end - start

def bench_chain(target_id: str, iterations: int):
    import itertools
    start = time.perf_counter()
    for _ in range(iterations):
        for c in itertools.chain.from_iterable(st.session_state.get("demo_comments", {}).values()):
            if c.get("comment_id") == target_id:
                res = str(c.get("author_email") or "")
                break
    end = time.perf_counter()
    return end - start

target_id = setup_data(1000, 10)
time_orig = bench_original(target_id, 100)
time_opt = bench_optimized(target_id, 100)
time_chain = bench_chain(target_id, 100)
print(f"Original: {time_orig:.4f} seconds")
print(f"Optimized: {time_opt:.4f} seconds")
print(f"Chain: {time_chain:.4f} seconds")
