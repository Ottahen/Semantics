"""The five phase views: startup, analysis, planning, execution, completion.

Each is a plain Textual `Container` (not a full `Screen`) because they
represent phases of one continuous run rather than separate navigable
pages — `pro.tui.app.SemanticsApp` swaps them in a `ContentSwitcher`
while the status header and command input stay docked in place.
"""

from .analysis import AnalysisView
from .completion import CompletionView
from .execution import ExecutionView
from .planning import PlanningView
from .startup import StartupView

__all__ = ["StartupView", "AnalysisView", "PlanningView", "ExecutionView", "CompletionView"]
