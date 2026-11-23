import json
import unittest

from app.services.codex_logs import tool_calls_from_transcript, turns_from_records


def event(seconds: int, kind: str, **payload) -> dict:
    return {
        "timestamp": f"2026-11-23T10:{seconds // 60:02d}:{seconds % 60:02d}Z",
        "type": "event_msg",
        "payload": {"type": kind, **payload},
    }


def response(seconds: int, kind: str, **payload) -> dict:
    return {**event(seconds, kind, **payload), "type": "response_item"}


class CodexTimingTests(unittest.TestCase):
    def test_completed_turns_exclude_time_between_turns(self) -> None:
        turns = turns_from_records([
            event(0, "task_started", turn_id="first"),
            event(10, "task_complete", turn_id="first"),
            event(20, "token_count"),
            event(600, "task_started", turn_id="second"),
            event(610, "task_complete", turn_id="second"),
        ])
        self.assertEqual(turns[0]["started_at"], "2026-11-23T10:00:00+00:00")
        self.assertEqual(turns[0]["ended_at"], "2026-11-23T10:00:10+00:00")
        self.assertEqual(turns[1]["started_at"], "2026-11-23T10:10:00+00:00")
        self.assertEqual(turns[1]["ended_at"], "2026-11-23T10:10:10+00:00")
        self.assertTrue(all(turn["status"] == "completed" for turn in turns))

    def test_incomplete_turn_ends_at_last_record_not_next_turn(self) -> None:
        turns = turns_from_records([
            event(0, "task_started", turn_id="incomplete"),
            response(2, "function_call", call_id="call", name="shell", arguments="pwd"),
            response(5, "function_call_output", call_id="call", output="/project"),
            event(7, "token_count"),
            event(600, "task_started", turn_id="next"),
        ])
        self.assertEqual(turns[0]["ended_at"], "2026-11-23T10:00:07+00:00")
        self.assertEqual(turns[0]["status"], "interrupted")
        self.assertEqual(turns[0]["events"][0]["ended_at"], "2026-11-23T10:00:05+00:00")
        self.assertNotIn("_last_recorded_at", turns[0])

    def test_aborted_turn_preserves_abort_time(self) -> None:
        for kind in ("turn_aborted", "task_aborted"):
            with self.subTest(kind=kind):
                turn = turns_from_records([
                    event(0, "task_started", turn_id="aborted"),
                    event(12, kind, turn_id="aborted"),
                    event(20, "token_count"),
                ])[0]
                self.assertEqual(turn["status"], "interrupted")
                self.assertEqual(turn["ended_at"], "2026-11-23T10:00:12+00:00")

    def test_out_of_order_records_keep_latest_known_time(self) -> None:
        turn = turns_from_records([
            event(0, "task_started", turn_id="ordered"),
            event(10, "token_count"),
            event(5, "token_count"),
        ])[0]
        self.assertEqual(turn["ended_at"], "2026-11-23T10:00:10+00:00")

    def test_tool_finish_time_is_retained_even_with_display_limit(self) -> None:
        records = [
            response(1, "function_call", call_id="one", name="shell", arguments="pwd"),
            response(2, "function_call", call_id="two", name="shell", arguments="ls"),
            response(4, "function_call_output", call_id="one", output="/project"),
            response(5, "function_call_output", call_id="two", output="file"),
        ]
        calls = tool_calls_from_transcript("\n".join(json.dumps(row) for row in records), limit=1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["output"], "/project")
        self.assertEqual(calls[0]["timestamp"], "2026-11-23T10:00:01+00:00")
        self.assertEqual(calls[0]["ended_at"], "2026-11-23T10:00:04+00:00")
