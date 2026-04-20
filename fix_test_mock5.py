import sys

def mock_cache_resource(*args, **kwargs):
    def decorator(func):
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            import types
            if isinstance(result, types.GeneratorType):
                # We fetch the first yielded value
                return next(result)
            return result
        return wrapper
    if len(args) == 1 and callable(args[0]):
        return decorator(args[0])
    return decorator
