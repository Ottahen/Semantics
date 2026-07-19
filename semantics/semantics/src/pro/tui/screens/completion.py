"""Screen 5 — Completion Screen.

Final summary report: files touched, lines changed, tokens/time spent,
and where the packaged artifact ZIP landed.
"""

from __future__ import annotations

from textual.containers import Vertical
from textual.widgets import Static


class CompletionView(Vertical):
    def compose(self):
        yield Static("[b]✅ TASK COMPLETED[/b]", classes="panel-title")
        yield Static("", id="summary-panel")
        yield Static("", id="tips-panel")

    def set_summary(
        self,
        files_changed: list[str],
        tokens_used: int,
        elapsed_seconds: float,
        model: str,
        artifact_path: str | None,
    ) -> None:
        files_block = "\n".join(f"   [#30d158]✅[/#30d158] {f}" for f in files_changed) or "   (no files changed)"
        text = (
            "[b]📊 SUMMARY REPORT[/b]\n\n"
            f"   📁 Files modified   {len(files_changed)}\n"
            f"   🧠 Tokens used      {tokens_used:,}\n"
            f"   ⚡ Total time       {elapsed_seconds:.1f}s\n"
            f"   🤖 Model            {model}\n\n"
            "[b]Changes:[/b]\n"
            f"{files_block}"
        )
        if artifact_path:
            text += f"\n\n   📦 Artifact created: {artifact_path}"
        self.query_one("#summary-panel", Static).update(text)

    def set_tips(self, tips: list[str]) -> None:
        self.query_one("#tips-panel", Static).update("\n".join(f"💡 {t}" for t in tips))
