import importlib
import json
import os
import unittest
from unittest import mock


class LibrarianApiTests(unittest.TestCase):
    def setUp(self):
        os.environ["SESSION_SECRET"] = "test-secret"
        os.environ.pop("TINYLYTICS_API_KEY", None)
        os.environ.pop("TINYLYTICS_SITE_ID", None)
        os.environ.pop("TINYLYTICS_ENABLED", None)
        os.environ.pop("LIBRARIAN_CONVERSATION_LOGGING", None)
        self.app = importlib.import_module("librarian_api.app")

    def tearDown(self):
        self.app.load_corpus.cache_clear()
        self.app.indexed_chunks.cache_clear()
        self.app.tinylytics_site_id.cache_clear()

    def test_session_token_round_trip_and_tamper_rejection(self):
        token = self.app.sign_payload({"sub": "abc", "exp": 9999999999})

        self.assertEqual(self.app.verify_token(token)["sub"], "abc")
        self.assertIsNone(self.app.verify_token(token + "x"))

    def test_subscriber_is_active_rejects_unsubscribed(self):
        self.assertTrue(self.app.subscriber_is_active({"type": "regular"}))
        self.assertFalse(self.app.subscriber_is_active({"type": "unactivated"}))
        self.assertFalse(self.app.subscriber_is_active({"type": "regular", "unsubscription_date": "2026-01-01"}))

    @mock.patch("librarian_api.app.fetch_subscriber")
    @mock.patch("librarian_api.app.dynamodb_table", return_value=None)
    def test_auth_handler_returns_token_for_active_subscriber(self, _table, fetch_subscriber):
        fetch_subscriber.return_value = {"type": "regular"}
        event = {"body": json.dumps({"email": "Reader@Example.com"})}

        response = self.app.auth_handler(event)
        body = json.loads(response["body"])

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(body["status"], "active")
        self.assertIn("token", body)

    @mock.patch("librarian_api.app.fetch_subscriber")
    @mock.patch("librarian_api.app.generate_premium_thank_you")
    @mock.patch("librarian_api.app.dynamodb_table", return_value=None)
    def test_auth_handler_returns_generated_premium_message_for_supporting_member(self, _table, generate_thank_you, fetch_subscriber):
        fetch_subscriber.return_value = {"type": "premium"}
        generate_thank_you.return_value = "Thingy appreciates your support as a Weekly Thing Supporting Member."
        event = {"body": json.dumps({"email": "supporter@example.com"})}

        response = self.app.auth_handler(event)
        body = json.loads(response["body"])

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(body["status"], "premium")
        self.assertIn("token", body)
        self.assertEqual(body["message"], "Thingy appreciates your support as a Weekly Thing Supporting Member.")
        generate_thank_you.assert_called_once()

    @mock.patch("librarian_api.app.fetch_subscriber")
    @mock.patch("librarian_api.app.generate_premium_thank_you", side_effect=ValueError("bad message"))
    @mock.patch("librarian_api.app.dynamodb_table", return_value=None)
    def test_auth_handler_uses_fallback_when_premium_message_generation_fails(self, _table, _generate_thank_you, fetch_subscriber):
        fetch_subscriber.return_value = {"type": "premium"}
        event = {"body": json.dumps({"email": "supporter@example.com"})}

        response = self.app.auth_handler(event)
        body = json.loads(response["body"])

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(body["status"], "premium")
        self.assertEqual(body["message"], "Thanks for being a Weekly Thing Supporting Member!")

    @mock.patch("librarian_api.app.fetch_subscriber", return_value=None)
    @mock.patch("librarian_api.app.dynamodb_table", return_value=None)
    def test_auth_handler_returns_not_found_status_for_missing_subscriber(self, _table, _fetch_subscriber):
        event = {"body": json.dumps({"email": "missing@example.com"})}

        response = self.app.auth_handler(event)
        body = json.loads(response["body"])

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(body["status"], "not_found")
        self.assertNotIn("token", body)

    @mock.patch("librarian_api.app.fetch_subscriber")
    @mock.patch("librarian_api.app.dynamodb_table", return_value=None)
    def test_auth_handler_returns_unconfirmed_status(self, _table, fetch_subscriber):
        fetch_subscriber.return_value = {"type": "unactivated"}
        event = {"body": json.dumps({"email": "reader@example.com"})}

        response = self.app.auth_handler(event)
        body = json.loads(response["body"])

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(body["status"], "unconfirmed")
        self.assertNotIn("token", body)

    @mock.patch("librarian_api.app.httpx.post")
    def test_create_subscriber_adds_librarian_source_tag(self, httpx_post):
        os.environ["BUTTONDOWN_API_KEY"] = "test-buttondown-key"
        api_response = mock.Mock(status_code=201)
        api_response.json.return_value = {"type": "unactivated"}
        httpx_post.return_value = api_response
        event = {"requestContext": {"http": {"sourceIp": "203.0.113.20"}}}

        subscriber = self.app.create_subscriber("reader@example.com", event)

        self.assertEqual(subscriber["type"], "unactivated")
        payload = httpx_post.call_args.kwargs["json"]
        self.assertEqual(payload["email_address"], "reader@example.com")
        self.assertEqual(payload["tags"], [self.app.LIBRARIAN_SOURCE_TAG_ID])
        self.assertEqual(payload["ip_address"], "203.0.113.20")

    @mock.patch("librarian_api.app.create_subscriber", return_value={"type": "unactivated"})
    @mock.patch("librarian_api.app.dynamodb_table", return_value=None)
    def test_auth_handler_subscribe_action_creates_unconfirmed_subscriber(self, _table, create_subscriber):
        event = {"body": json.dumps({"email": "new@example.com", "action": "subscribe"})}

        response = self.app.auth_handler(event)
        body = json.loads(response["body"])

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(body["status"], "subscribed")
        self.assertEqual(body["subscriber_status"], "unconfirmed")
        create_subscriber.assert_called_once()

    @mock.patch("librarian_api.app.send_subscriber_reminder")
    @mock.patch("librarian_api.app.dynamodb_table", return_value=None)
    def test_auth_handler_resend_confirmation_action_sends_reminder(self, _table, send_reminder):
        event = {"body": json.dumps({"email": "reader@example.com", "action": "resend_confirmation"})}

        response = self.app.auth_handler(event)
        body = json.loads(response["body"])

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(body["status"], "reminder_sent")
        send_reminder.assert_called_once_with("reader@example.com")

    @mock.patch("librarian_api.app.fetch_subscriber")
    @mock.patch("librarian_api.app.log_event")
    @mock.patch("librarian_api.app.check_rate_limit", return_value=False)
    @mock.patch("librarian_api.app.dynamodb_table", return_value=object())
    def test_auth_handler_rate_limits_before_subscriber_lookup(self, _table, _limit, _log, fetch_subscriber):
        event = {
            "body": json.dumps({"email": "reader@example.com"}),
            "requestContext": {"http": {"sourceIp": "203.0.113.10"}},
            "headers": {"user-agent": "test"},
        }

        response = self.app.auth_handler(event)

        self.assertEqual(response["statusCode"], 429)
        fetch_subscriber.assert_not_called()

    def test_prompts_handler_rejects_invalid_token(self):
        event = {"body": json.dumps({})}

        response = self.app.prompts_handler(event)

        self.assertEqual(response["statusCode"], 401)

    @mock.patch("librarian_api.app.generate_prompts")
    @mock.patch("librarian_api.app.dynamodb_table", return_value=None)
    def test_prompts_handler_returns_three_generated_prompts(self, _table, generate_prompts):
        generate_prompts.return_value = [
            {"label": "Open web", "question": "What does the archive say about the open web?"},
            {"label": "AI writing", "question": "Where has AI writing appeared in the archive?"},
            {"label": "Personal systems", "question": "What themes appear around personal systems?"},
        ]
        token = self.app.sign_payload({"sub": "abc", "exp": 9999999999})
        event = {"body": json.dumps({"token": token})}

        response = self.app.prompts_handler(event)
        body = json.loads(response["body"])

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(body["source"], "generated")
        self.assertEqual(len(body["prompts"]), 3)

    @mock.patch("librarian_api.app.generate_prompts", side_effect=ValueError("bad prompts"))
    @mock.patch("librarian_api.app.dynamodb_table", return_value=None)
    def test_prompts_handler_falls_back_when_generation_fails(self, _table, _generate_prompts):
        token = self.app.sign_payload({"sub": "abc", "exp": 9999999999})
        event = {"body": json.dumps({"token": token})}

        response = self.app.prompts_handler(event)
        body = json.loads(response["body"])

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(body["source"], "fallback")
        self.assertEqual(len(body["prompts"]), 3)

    @mock.patch("librarian_api.app.generate_prompts")
    @mock.patch("librarian_api.app.check_rate_limit", return_value=True)
    @mock.patch("librarian_api.app.dynamodb_table", return_value=object())
    def test_prompts_handler_rate_limits_by_session(self, _table, check_rate_limit, generate_prompts):
        generate_prompts.return_value = [
            {"label": "One", "question": "Question one?"},
            {"label": "Two", "question": "Question two?"},
            {"label": "Three", "question": "Question three?"},
        ]
        token = self.app.sign_payload({"sid": "session-123", "sub": "abc", "exp": 9999999999})
        event = {"body": json.dumps({"token": token})}

        response = self.app.prompts_handler(event)

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(check_rate_limit.call_args.args[1], "prompts#session-123")

    def test_sanitize_prompts_requires_three_items(self):
        long_label = "How do Banff and Sunrise portray landscape, vision, and sense of place?"
        long_question = "What can Thingy show me about privacy, security, tokens, and how the archive's framing changes across multiple issues without truncating the actual question text?"
        prompts = self.app.sanitize_prompts(
            {
                "prompts": [
                    {"label": long_label, "question": long_question},
                    {"label": "Two", "question": "Question two?"},
                    {"label": "Three", "question": "Question three?"},
                ]
            }
        )

        self.assertEqual(len(prompts), 3)
        self.assertEqual(prompts[0]["label"], long_label[:72])
        self.assertEqual(prompts[0]["question"], long_question[:220])

    @mock.patch("librarian_api.app.httpx.post")
    def test_generate_prompts_uses_low_reasoning_and_parses_response(self, httpx_post):
        os.environ["OPENAI_API_KEY"] = "test-key"
        response = mock.Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps(
                                {
                                    "prompts": [
                                        {"label": "One", "question": "Question one?"},
                                        {"label": "Two", "question": "Question two?"},
                                        {"label": "Three", "question": "Question three?"},
                                    ]
                                }
                            ),
                        }
                    ],
                }
            ],
        }
        httpx_post.return_value = response

        prompts = self.app.generate_prompts()

        self.assertEqual(len(prompts), 3)
        payload = httpx_post.call_args.kwargs["json"]
        self.assertEqual(payload["reasoning"], {"effort": "low"})
        self.assertEqual(payload["text"]["verbosity"], "low")
        self.assertIn("easy ways to start talking", payload["input"])
        self.assertIn("under 8 words", payload["instructions"])
        self.assertIn("personal, genuine, friendly", payload["instructions"])
        self.assertGreaterEqual(payload["max_output_tokens"], 1400)

    @mock.patch("librarian_api.app.httpx.post")
    def test_generate_prompts_rejects_incomplete_openai_response(self, httpx_post):
        os.environ["OPENAI_API_KEY"] = "test-key"
        response = mock.Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "status": "incomplete",
            "incomplete_details": {"reason": "max_output_tokens"},
            "output": [{"type": "reasoning", "summary": []}],
        }
        httpx_post.return_value = response

        with self.assertRaisesRegex(ValueError, "incomplete prompts"):
            self.app.generate_prompts()

    def test_sanitize_history_keeps_recent_user_and_assistant_messages(self):
        history = self.app.sanitize_history(
            [
                {"role": "system", "content": "ignore"},
                {"role": "user", "content": "What about RSS?\n"},
                {"role": "assistant", "content": "RSS matters.  "},
            ]
        )

        self.assertEqual(
            history,
            [
                {"role": "user", "content": "What about RSS?"},
                {"role": "assistant", "content": "RSS matters."},
            ],
        )

    def test_retrieval_query_includes_conversation_context(self):
        query = self.app.retrieval_query(
            "Tell me more about that.",
            [{"role": "user", "content": "What has the archive said about RSS?"}],
        )

        self.assertIn("What has the archive said about RSS?", query)
        self.assertIn("Tell me more about that.", query)

    def test_build_prompt_includes_jamie_pronouns(self):
        prompt = self.app.build_prompt(
            "Who is Jamie?",
            [
                {
                    "issue_number": 1,
                    "subject": "Test",
                    "publish_date": "2026-01-01",
                    "section": "Intro",
                    "url": "/archive/1/",
                    "text": "Jamie wrote this.",
                }
            ],
        )

        self.assertIn("use he/him pronouns", prompt)
        self.assertIn("Source kind:", prompt)
        self.assertIn("Age:", prompt)
        self.assertIn("warm, genuinely curious librarian", prompt)
        self.assertIn("not like a search-results report", prompt)
        self.assertIn("personal, friendly vibe", prompt)

    def test_polish_answer_removes_customer_support_closing(self):
        answer = self.app.polish_answer(
            "RSS became a way to keep agency in reading (#343).\n\n"
            "If you want, I can pull a reading path together next."
        )

        self.assertEqual(answer, "RSS became a way to keep agency in reading (#343).")

    def test_retrieve_blends_recency_and_graph_candidates(self):
        self.app.indexed_chunks.cache_clear()
        self.app.load_corpus.cache_clear()
        with mock.patch(
            "librarian_api.app.load_corpus",
            return_value={
                "topics": [
                    {
                        "name": "AI and agents",
                        "description": "Archive material related to AI agents.",
                        "issue_numbers": [1, 2],
                    }
                ],
                "issues": [
                    {
                        "number": 1,
                        "subject": "Old AI",
                        "publish_date": "2018-01-01T00:00:00Z",
                        "issue_year": 2018,
                        "url": "/archive/1/",
                        "topics": ["AI and agents"],
                        "summary": {"abstract": "Early notes about AI agents.", "key_points": []},
                    },
                    {
                        "number": 2,
                        "subject": "Recent AI",
                        "publish_date": "2026-01-01T00:00:00Z",
                        "issue_year": 2026,
                        "url": "/archive/2/",
                        "topics": ["AI and agents"],
                        "summary": {"abstract": "Recent notes about AI agents.", "key_points": []},
                    },
                ],
                "chunks": [
                    {
                        "id": "old",
                        "issue_number": 1,
                        "subject": "Old AI",
                        "publish_date": "2018-01-01T00:00:00Z",
                        "issue_year": 2018,
                        "section": "AI",
                        "text": "AI agents and assistants",
                        "url": "/archive/1/",
                        "topics": ["AI and agents"],
                    },
                    {
                        "id": "recent",
                        "issue_number": 2,
                        "subject": "Recent AI",
                        "publish_date": "2026-01-01T00:00:00Z",
                        "issue_year": 2026,
                        "section": "AI",
                        "text": "AI agents and assistants",
                        "url": "/archive/2/",
                        "topics": ["AI and agents"],
                    },
                ],
            },
        ):
            self.app.indexed_chunks.cache_clear()
            matches = self.app.retrieve("What is current with AI agents?", limit=4)

        self.assertEqual(matches[0]["issue_number"], 2)
        self.assertTrue(any(match.get("source_kind") == "issue_summary" for match in matches))
        self.assertIn("age_label", matches[0])

    def test_cors_origin_matches_allowed_request_origin(self):
        os.environ["ALLOWED_ORIGIN"] = "https://weekly.thingelstad.com,http://localhost:8080"
        event = {"headers": {"origin": "http://localhost:8080"}}

        response = self.app.json_response(200, {"ok": True}, event=event)

        self.assertEqual(response["headers"]["access-control-allow-origin"], "http://localhost:8080")

    @mock.patch("librarian_api.app.httpx.post")
    def test_tinylytics_event_posts_expected_payload(self, httpx_post):
        os.environ["TINYLYTICS_API_KEY"] = "tly-fa-test"
        os.environ["TINYLYTICS_SITE_ID"] = "456"
        response = mock.Mock()
        response.raise_for_status.return_value = None
        httpx_post.return_value = response
        event = {
            "headers": {"user-agent": "Unit Test"},
            "requestContext": {"http": {"sourceIp": "203.0.113.50"}},
        }

        self.app.post_tinylytics_event(
            event,
            "librarian.chat_success",
            visitor_id="hash-123",
            value=self.app.tinylytics_value(member="hash-123", citations=3),
        )

        self.assertEqual(httpx_post.call_args.args[0], "https://tinylytics.app/api/v1/sites/456/events")
        self.assertEqual(httpx_post.call_args.kwargs["headers"]["Authorization"], "Bearer tly-fa-test")
        payload = httpx_post.call_args.kwargs["json"]
        self.assertEqual(payload["event"], "librarian.chat_success")
        self.assertEqual(payload["visitor_id"], "hash-123")
        self.assertEqual(payload["value"], "member=hash-123;citations=3")
        self.assertEqual(payload["path"], "/librarian/api")
        self.assertEqual(payload["source"], "librarian-api")
        self.assertEqual(payload["ip_address"], "203.0.113.50")
        self.assertNotIn("user_agent", payload)

    @mock.patch("librarian_api.app.httpx.post")
    def test_tinylytics_event_failure_is_non_fatal(self, _httpx_post):
        os.environ["TINYLYTICS_API_KEY"] = "tly-fa-test"
        _httpx_post.side_effect = Exception("network")

        with self.assertLogs("librarian_api.app", level="WARNING") as logs:
            self.app.post_tinylytics_event({}, "librarian.chat_success", visitor_id="hash-123")

        self.assertIn("tinylytics_event_failed", "\n".join(logs.output))

    @mock.patch("librarian_api.app.httpx.get")
    def test_tinylytics_site_id_resolves_public_uid(self, httpx_get):
        os.environ["TINYLYTICS_API_KEY"] = "tly-fa-test"
        os.environ["TINYLYTICS_SITE_ID"] = "public-uid"
        response = mock.Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"sites": [{"id": 456, "uid": "public-uid", "url": "https://weekly.thingelstad.com"}]}
        httpx_get.return_value = response

        self.assertEqual(self.app.tinylytics_site_id(), "456")

    @mock.patch("librarian_api.app.fetch_subscriber")
    @mock.patch("librarian_api.app.generate_premium_thank_you", return_value="Generated premium thanks.")
    @mock.patch("librarian_api.app.post_tinylytics_event")
    @mock.patch("librarian_api.app.dynamodb_table", return_value=None)
    def test_auth_handler_posts_tinylytics_success_event(self, _table, post_tinylytics, _generate_thank_you, fetch_subscriber):
        fetch_subscriber.return_value = {"type": "premium"}
        event = {"body": json.dumps({"email": "Reader@Example.com"})}

        response = self.app.auth_handler(event)

        self.assertEqual(response["statusCode"], 200)
        post_tinylytics.assert_called_once()
        self.assertEqual(post_tinylytics.call_args.args[1], "librarian.auth_success")
        self.assertEqual(post_tinylytics.call_args.kwargs["visitor_id"], self.app.email_hash("reader@example.com"))

    @mock.patch("librarian_api.app.generate_prompts")
    @mock.patch("librarian_api.app.post_tinylytics_event")
    @mock.patch("librarian_api.app.dynamodb_table", return_value=None)
    def test_prompts_handler_posts_tinylytics_event(self, _table, post_tinylytics, generate_prompts):
        generate_prompts.return_value = [
            {"label": "One", "question": "Question one?"},
            {"label": "Two", "question": "Question two?"},
            {"label": "Three", "question": "Question three?"},
        ]
        token = self.app.sign_payload({"sub": "abc", "exp": 9999999999})
        event = {"body": json.dumps({"token": token})}

        response = self.app.prompts_handler(event)

        self.assertEqual(response["statusCode"], 200)
        post_tinylytics.assert_called_once()
        self.assertEqual(post_tinylytics.call_args.args[1], "librarian.prompts_generated")
        self.assertEqual(post_tinylytics.call_args.kwargs["visitor_id"], "abc")
        self.assertIn("source=generated", post_tinylytics.call_args.kwargs["value"])

    @mock.patch("librarian_api.app.call_openai", return_value="Answer citing #1.")
    @mock.patch("librarian_api.app.retrieve")
    @mock.patch("librarian_api.app.post_tinylytics_event")
    @mock.patch("librarian_api.app.dynamodb_table", return_value=None)
    def test_chat_handler_posts_success_tinylytics_event(self, _table, post_tinylytics, retrieve, _call_openai):
        retrieve.return_value = [
            {"issue_number": 1, "subject": "RSS", "section": "Open Web", "url": "/archive/1/"}
        ]
        token = self.app.sign_payload({"sub": "abc", "exp": 9999999999})
        event = {"body": json.dumps({"token": token, "message": "What about RSS?"})}

        response = self.app.chat_handler(event)

        self.assertEqual(response["statusCode"], 200)
        post_tinylytics.assert_called_once()
        self.assertEqual(post_tinylytics.call_args.args[1], "librarian.chat_success")
        self.assertIn("citations=1", post_tinylytics.call_args.kwargs["value"])

    def test_record_conversation_writes_reviewable_chat_item(self):
        table = mock.Mock()
        event = {"requestContext": {"requestId": "req-123"}}
        citations = [{"issue_number": 1, "subject": "RSS", "section": "Open Web", "url": "/archive/1/"}]

        self.app.record_conversation(
            table,
            event=event,
            subscriber_hash="sub-hash",
            question="What about RSS?",
            answer="RSS matters (#1).",
            history_count=2,
            citations=citations,
            route="chat",
        )

        item = table.put_item.call_args.kwargs["Item"]
        self.assertTrue(item["pk"].startswith("conversation#"))
        self.assertEqual(item["sk"], "chat")
        self.assertEqual(item["request_id"], "req-123")
        self.assertEqual(item["subscriber_hash"], "sub-hash")
        self.assertEqual(item["question"], "What about RSS?")
        self.assertEqual(item["answer"], "RSS matters (#1).")
        self.assertEqual(item["source_issues"], ["1"])
        self.assertEqual(item["citations"], citations)
        self.assertIn("ttl", item)

    @mock.patch("librarian_api.app.call_openai", return_value="Answer citing #1.")
    @mock.patch("librarian_api.app.retrieve")
    @mock.patch("librarian_api.app.post_tinylytics_event")
    @mock.patch("librarian_api.app.check_rate_limit", return_value=True)
    def test_chat_handler_records_successful_conversation(self, _check_rate_limit, _post_tinylytics, retrieve, _call_openai):
        table = mock.Mock()
        retrieve.return_value = [
            {"issue_number": 1, "subject": "RSS", "section": "Open Web", "url": "/archive/1/"}
        ]
        token = self.app.sign_payload({"sub": "abc", "exp": 9999999999})
        event = {
            "requestContext": {"requestId": "req-chat"},
            "body": json.dumps({"token": token, "message": "What about RSS?"}),
        }

        with mock.patch("librarian_api.app.dynamodb_table", return_value=table):
            response = self.app.chat_handler(event)

        self.assertEqual(response["statusCode"], 200)
        item = table.put_item.call_args.kwargs["Item"]
        self.assertEqual(item["request_id"], "req-chat")
        self.assertEqual(item["subscriber_hash"], "abc")
        self.assertEqual(item["question"], "What about RSS?")
        self.assertEqual(item["answer"], "Answer citing #1.")

    @mock.patch("librarian_api.app.retrieve", return_value=[])
    @mock.patch("librarian_api.app.post_tinylytics_event")
    @mock.patch("librarian_api.app.dynamodb_table", return_value=None)
    def test_chat_handler_posts_no_sources_tinylytics_event(self, _table, post_tinylytics, _retrieve):
        token = self.app.sign_payload({"sub": "abc", "exp": 9999999999})
        event = {"body": json.dumps({"token": token, "message": "What about something obscure?"})}

        response = self.app.chat_handler(event)

        self.assertEqual(response["statusCode"], 200)
        post_tinylytics.assert_called_once()
        self.assertEqual(post_tinylytics.call_args.args[1], "librarian.chat_no_sources")

    @mock.patch("librarian_api.app.auth_handler", side_effect=RuntimeError("boom"))
    def test_handler_logs_and_returns_json_for_unhandled_exception(self, _auth_handler):
        event = {
            "requestContext": {"requestId": "req-123", "http": {"method": "POST"}},
            "rawPath": "/auth",
            "headers": {"origin": "https://weekly.thingelstad.com"},
            "body": "{}",
        }

        with self.assertLogs("librarian_api.app", level="ERROR") as logs:
            response = self.app.handler(event, context=None)

        self.assertEqual(response["statusCode"], 500)
        self.assertEqual(response["headers"]["x-request-id"], "req-123")
        self.assertIn("request_failed", "\n".join(logs.output))

    def test_health_handler_is_cheap_and_json(self):
        event = {
            "requestContext": {"requestId": "req-health", "http": {"method": "GET"}},
            "rawPath": "/health",
            "headers": {"origin": "https://weekly.thingelstad.com"},
        }

        response = self.app.handler(event, context=None)
        body = json.loads(response["body"])

        self.assertEqual(response["statusCode"], 200)
        self.assertTrue(body["ok"])
        self.assertEqual(response["headers"]["x-request-id"], "req-health")

    def test_retrieve_finds_matching_chunks(self):
        self.app.indexed_chunks.cache_clear()
        self.app.load_corpus.cache_clear()
        with mock.patch(
            "librarian_api.app.load_corpus",
            return_value={
                "chunks": [
                    {
                        "issue_number": 1,
                        "subject": "RSS",
                        "section": "Open Web",
                        "text": "RSS feeds and personal websites",
                        "url": "/archive/1/",
                    },
                    {
                        "issue_number": 2,
                        "subject": "Cooking",
                        "section": "Food",
                        "text": "Pasta and sauce",
                        "url": "/archive/2/",
                    },
                ]
            },
        ):
            self.app.indexed_chunks.cache_clear()
            matches = self.app.retrieve("personal RSS websites")

        self.assertEqual(matches[0]["issue_number"], 1)


if __name__ == "__main__":
    unittest.main()
