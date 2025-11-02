import inspect
import sys
import typing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Compatibility shim: pydantic 1.x expects ForwardRef._evaluate to accept a positional
# ``recursive_guard`` argument, but Python 3.12 makes it keyword-only.
_forward_ref_evaluate = getattr(typing.ForwardRef, "_evaluate", None)
if _forward_ref_evaluate is not None:
    signature = inspect.signature(_forward_ref_evaluate)
    parameter = signature.parameters.get("recursive_guard")
    if parameter is not None and parameter.kind is inspect.Parameter.KEYWORD_ONLY:

        def _patched_forward_ref_evaluate(self, globalns, localns, *args, **kwargs):
            recursive_guard = kwargs.get("recursive_guard")
            if args:
                recursive_guard = args[0]
            if recursive_guard is None:
                recursive_guard = set()
            return _forward_ref_evaluate(self, globalns, localns, recursive_guard=recursive_guard)

        typing.ForwardRef._evaluate = _patched_forward_ref_evaluate  # type: ignore[attr-defined]
