import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from curator import config as cfg
from curator import query, search, constants as consts


class DummyClient:
    def chat_stream(self, messages, temperature=0.0):  # noqa: ARG002
        yield "Answer with only L2 evidence."

    def unload(self) -> None:
        return None


class FailingTranslateClient(DummyClient):
    def chat(self, messages, temperature=0.0):  # noqa: ARG002
        raise RuntimeError("translator unavailable")


class DummyCallbacks(query.QueryCallbacks):
    def __init__(self) -> None:
        self.saved_paths: list[str] = []
        self.errors: list[str] = []
        self.completed: query.QueryResult | None = None

    def on_start(self, question: str, mode: str) -> None:
        return None

    def on_classifying_intent(self) -> None:
        return None

    def on_intent_classified(self, intent: str) -> None:
        return None

    def on_chitchat_reply(self, reply: str) -> None:
        return None

    def on_searching(self) -> None:
        return None

    def on_search_done(self, results: search.SearchResults) -> None:
        return None

    def on_no_results(self) -> None:
        return None

    def on_synthesizing(self) -> None:
        return None

    def on_stream_chunk(self, chunk: str) -> None:
        return None

    def on_saved(self, saved_path: str) -> None:
        self.saved_paths.append(saved_path)

    def on_complete(self, result: query.QueryResult) -> None:
        self.completed = result

    def on_error(self, error: str) -> None:
        self.errors.append(error)


class DummyHit:
    def __init__(self, full_path: str):
        self.full_path = full_path


class QueryExhibitionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.paths = cfg.paths_from_config(self.root)
        self.paths.exhibitions.mkdir(parents=True, exist_ok=True)
        self.paths.concepts.mkdir(parents=True, exist_ok=True)
        self.paths.atoms.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_save_curation_page_raises_without_l3_concepts(self) -> None:
        # Create an answer and hits that DO NOT contain any L3 Concepts.
        answer = "This is a chat session answer with no L3 concepts."
        hits = [DummyHit(f"{consts.LAYER_L2}/ATM-1234.md")]

        # This should raise ValueError because there are no L3 concepts.
        with self.assertRaises(ValueError) as ctx:
            query._save_curation_page(
                paths=self.paths,
                question="What is this?",
                answer=answer,
                title="Session Chat",
                hits=hits,
                ephemeral=False,
            )
        self.assertIn("no related L3 Concepts", str(ctx.exception))

    def test_run_query_returns_answer_when_l4_save_has_no_l3_concepts(self) -> None:
        callbacks = DummyCallbacks()
        hit = search.SearchHit(
            full_path=f"{consts.LAYER_L2}/ATM-1234.md",
            title="Atom only",
            score=0.9,
            full_content="Only atom-level evidence is available.",
        )
        results = search.SearchResults(hits=[hit])

        with (
            patch.object(query, "translate_to_english", return_value="What is this?"),
            patch.object(query.search, "query", return_value=results),
        ):
            result = query.run_query(
                paths=self.paths,
                client=DummyClient(),
                question="What is this?",
                callbacks=callbacks,
                save_as="Session Chat",
                classify_intent_first=False,
                ephemeral_exhibition=False,
            )

        self.assertTrue(result.ok)
        self.assertEqual(result.answer, "Answer with only L2 evidence.")
        self.assertIsNone(result.saved_path)
        self.assertEqual(callbacks.saved_paths, [])
        self.assertEqual(callbacks.errors, [])
        self.assertIs(callbacks.completed, result)
        self.assertEqual(list(self.paths.exhibitions.glob("*.md")), [])

    def test_synthesis_prompt_truncates_oversized_sources(self) -> None:
        huge_content = "A" * (query.MAX_SYNTHESIS_SOURCE_CHARS + 1000)
        hit = search.SearchHit(
            full_path=f"{consts.LAYER_L1}/CTX-large.md",
            title="Oversized source",
            score=0.9,
            full_content=huge_content,
        )
        prompt = query._build_synthesis_user_prompt(
            "What is this?",
            search.SearchResults(hits=[hit]),
        )

        self.assertIn("[... source truncated for synthesis prompt ...]", prompt)
        self.assertNotIn("A" * (query.MAX_SYNTHESIS_SOURCE_CHARS + 1), prompt)
        self.assertLess(len(prompt), query.MAX_SYNTHESIS_SOURCE_CHARS + 2000)

    def test_run_query_retries_unboosted_query_after_scoped_empty_results(self) -> None:
        callbacks = DummyCallbacks()
        l1_result = search.SearchResults(hits=[
            search.SearchHit(
                full_path=f"{consts.LAYER_L1}/CTX-noise.md",
                title="Context",
                score=0.8,
                full_content="Context-only hit.",
            )
        ])
        l3_result = search.SearchResults(hits=[
            search.SearchHit(
                full_path=f"{consts.LAYER_L3}/CON-good1234.md",
                title="Concept",
                score=0.4,
                full_content="Concept evidence.",
            )
        ])

        with (
            patch.object(query, "translate_to_english", return_value="What role does X play?"),
            patch.object(query.search, "query", side_effect=[l1_result, l3_result]) as search_mock,
        ):
            result = query.run_query(
                paths=self.paths,
                client=DummyClient(),
                question="X는 어떤 역할인가요?",
                callbacks=callbacks,
                classify_intent_first=False,
                scope="concepts",
                query_boost_terms=["unhelpful-boost"],
            )

        self.assertTrue(result.ok)
        self.assertEqual(search_mock.call_count, 2)
        self.assertEqual(result.hits[0].full_path, f"{consts.LAYER_L3}/CON-good1234.md")

    def test_run_query_saves_workspace_ephemeral_exhibition_for_cache(self) -> None:
        callbacks = DummyCallbacks()
        concept_path = self.paths.concepts / "CON-work1234.md"
        concept_path.write_text(
            """---
id: CON-work1234
type: concept
name: Workspace Concept
domain: Test
confidence_score: 0.8
---

# Workspace Concept
""",
            encoding="utf-8",
        )
        hit = search.SearchHit(
            full_path=f"{consts.LAYER_L3}/CON-work1234.md",
            title="Workspace Concept",
            score=0.9,
            full_content=concept_path.read_text(encoding="utf-8"),
        )

        with (
            patch.object(query, "translate_to_english", return_value="What is this?"),
            patch.object(query.search, "query", return_value=search.SearchResults(hits=[hit])),
        ):
            result = query.run_query(
                paths=self.paths,
                client=DummyClient(),
                question="What is this?",
                callbacks=callbacks,
                save_as="What is this?",
                classify_intent_first=False,
                workspace_project="Workspace Project",
                workspace_path="/tmp/Workspace",
                cache_key="workspace-cache-key",
                ephemeral_exhibition=False,
            )

        self.assertTrue(result.ok)
        self.assertIsNotNone(result.saved_path)
        self.assertEqual(callbacks.saved_paths, [result.saved_path])
        saved = next(self.paths.exhibitions.glob(f"{consts.PREFIX_L4}-*.md"))
        saved_text = saved.read_text(encoding="utf-8")
        self.assertIn("workspace_path: /tmp/Workspace", saved_text)
        self.assertIn("cache_key: workspace-cache-key", saved_text)
        self.assertIn("ephemeral: false", saved_text)
        self.assertIn("exhibition_origin: query_gen", saved_text)
        self.assertIn(f"- {consts.LAYER_L3}/CON-work1234", saved_text)

    def test_translate_to_english_uses_ascii_terms_when_translation_fails(self) -> None:
        translated = query.translate_to_english(
            FailingTranslateClient(),
            "2D Gaussian Splatting에서 dual absolute quadric은 어떤 역할을 하나요?",
        )

        self.assertEqual(translated, "2D Gaussian Splatting dual absolute quadric")

    def test_run_query_uses_explicit_english_query_metadata(self) -> None:
        callbacks = DummyCallbacks()
        hit = search.SearchHit(
            full_path=f"{consts.LAYER_L3}/CON-lang1234.md",
            title="Concept",
            score=0.9,
            full_content="English evidence about projective geometry.",
        )
        results = search.SearchResults(hits=[hit])
        searched: list[str] = []
        prompts_seen: list[str] = []

        class PromptCapturingClient(DummyClient):
            def chat_stream(self, messages, temperature=0.0):  # noqa: ARG002
                prompts_seen.append(messages[-1].content)
                yield "한국어 답변"

        def fake_search(paths, question, **kwargs):  # noqa: ARG001
            searched.append(question)
            return results

        with (
            patch.object(query, "translate_to_english", side_effect=AssertionError("should not translate again")),
            patch.object(query.search, "query", side_effect=fake_search),
        ):
            result = query.run_query(
                paths=self.paths,
                client=PromptCapturingClient(),
                question="이 개념은 무엇을 의미하나요?",
                callbacks=callbacks,
                save_as="",
                classify_intent_first=False,
                english_query="What does this concept mean?",
                input_language="Korean",
                final_output_language="Korean",
            )

        self.assertTrue(result.ok)
        self.assertEqual(result.english_query, "What does this concept mean?")
        self.assertEqual(result.input_language, "Korean")
        self.assertEqual(result.final_output_language, "Korean")
        self.assertEqual(searched[0], "What does this concept mean?")
        self.assertIn("Original user question: 이 개념은 무엇을 의미하나요?", prompts_seen[0])
        self.assertIn("English working query: What does this concept mean?", prompts_seen[0])
        self.assertIn("Final output language: Korean", prompts_seen[0])


if __name__ == "__main__":
    unittest.main()
