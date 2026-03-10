import threading
import queue


def execute_safely(func, *args, **kwargs):
    q = queue.Queue()
    def wrapper():
        try:
            res = func(*args, **kwargs)
            q.put(("SUCCESS", res))
        except Exception as e:
            q.put(("ERROR", e))
    t = threading.Thread(target=wrapper)
    t.start()
    t.join()
    status, res = q.get()
    if status == "ERROR":
        raise res
    return res


def parse_chatbot_id(id_str: str) -> int:
    """Parse 'CB001' or '1' style chatbot identifiers to an int."""
    return int(id_str[2:]) if id_str.startswith("CB") else int(id_str)
