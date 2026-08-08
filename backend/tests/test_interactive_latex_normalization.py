"""v0.52.1: interactive LaTeX transcription must not delete numeric content.

`_CLI_NOISE_RE` carries a digits-only alternative so an agentic CLI's trailing
"tokens used / 12,345" banner is stripped. `normalize_interactive_latex_transcription`
was re-applying that whole noise filter to the text INSIDE the model's
`<transcription>` block, where banners cannot occur — so an equation number, a
table cell, or a page number on its own line was deleted from a faithful
transcription. When the selection was entirely numeric the result was empty, and
the plugin reported the empty result as an LLM-provider misconfiguration.
"""

import unittest

from curator import vision


class TestInteractiveLatexNormalization(unittest.TestCase):
    def test_bare_number_inside_the_transcription_block_survives(self) -> None:
        self.assertEqual(
            vision.normalize_interactive_latex_transcription("<transcription>1</transcription>"),
            "1",
        )

    def test_numeric_line_among_prose_survives(self) -> None:
        raw = "<transcription>The eigenvalue is\n2\nfor this system.</transcription>"
        self.assertEqual(
            vision.normalize_interactive_latex_transcription(raw),
            "The eigenvalue is\n2\nfor this system.",
        )

    def test_multi_row_numeric_table_survives(self) -> None:
        raw = "<transcription>1\n2\n3</transcription>"
        self.assertEqual(vision.normalize_interactive_latex_transcription(raw), "1\n2\n3")

    def test_comma_grouped_number_survives(self) -> None:
        """`\\d[\\d,]*` was written for `12,345` token counts; a real figure looks the same."""
        raw = "<transcription>11,052</transcription>"
        self.assertEqual(vision.normalize_interactive_latex_transcription(raw), "11,052")

    def test_cli_banner_outside_the_block_is_still_stripped(self) -> None:
        """The noise filter must keep working where banners actually appear."""
        raw = "codex\n1234\n<transcription>$x^2$</transcription>\ntokens used\n5678"
        self.assertEqual(vision.normalize_interactive_latex_transcription(raw), "$x^2$")

    def test_untagged_output_still_has_banners_stripped(self) -> None:
        """With no block to trust, the whole text stays subject to the filter."""
        raw = "codex\n$E = mc^2$\ntokens used"
        self.assertEqual(vision.normalize_interactive_latex_transcription(raw), "$E = mc^2$")

    def test_intro_and_outro_prose_are_still_stripped(self) -> None:
        raw = (
            "<transcription>Here is the transcription:\n"
            "$a + b$\n"
            "This preserves the original formula.</transcription>"
        )
        self.assertEqual(vision.normalize_interactive_latex_transcription(raw), "$a + b$")

    def test_code_fences_inside_the_block_are_still_dropped(self) -> None:
        raw = "<transcription>```latex\n$x$\n```</transcription>"
        self.assertEqual(vision.normalize_interactive_latex_transcription(raw), "$x$")

    def test_display_math_wrapper_inside_the_block_is_still_unwrapped(self) -> None:
        raw = "<transcription>$$x^2 + y^2 = r^2$$</transcription>"
        self.assertEqual(
            vision.normalize_interactive_latex_transcription(raw),
            "x^2 + y^2 = r^2",
        )

    def test_full_page_ingest_path_is_unchanged(self) -> None:
        """`normalize_vision_latex` keeps its banner-stripping contract verbatim."""
        self.assertEqual(vision.normalize_vision_latex("codex\n$x$\n1234"), "$x$")


if __name__ == "__main__":
    unittest.main()
