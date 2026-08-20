from typing import Callable, Optional, Union

def create_event_decorator(deco_method: Callable, event_type: str):
    """
    装饰器工厂，用于在 QueQiao 中批量创建装饰器
    """
    def decorator(
            arg: Optional[Union[str, Callable]] = None,
            *extra_event_names: str
    ) -> Callable:
        def _decorate(func: Callable) -> Callable:
            if isinstance(arg, str):
                event_names = [f"{event_type}.{arg}"] + [
                    f"{event_type}.{e}" for e in extra_event_names
                ]
            else:
                event_names = [event_type]

            return deco_method(*event_names)(func)

        if callable(arg):
            return _decorate(arg)
        return _decorate

    return decorator