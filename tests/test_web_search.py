"""Exercise the voice-agent dispatcher and real MCP SDK without Pi hardware.

HTTP fixtures replace the network; Ollama replies are scripted, not model runs.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
import uuid
from unittest.mock import Mock, MagicMock, patch

import httpx
# Load SDK annotations before replacing the HTTP client constructor.
from mcp.client.streamable_http import streamable_http_client

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from web_search import PARALLEL_MCP_URL, USER_AGENT

# Only hardware/model dependencies are replaced. web_search, HTTPX and the MCP
# SDK are real. Importing agent.py never starts its GUI's __main__ entrypoint.
STUBS = {name: MagicMock() for name in (
    'tkinter', 'tkinter.ttk', 'PIL', 'sounddevice', 'numpy', 'scipy',
    'scipy.signal', 'openwakeword', 'openwakeword.model', 'ollama',
    'duckduckgo_search',
)}
spec = importlib.util.spec_from_file_location('agent_under_test', ROOT / 'agent.py')
agent = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, STUBS):
    spec.loader.exec_module(agent)

REAL_ASYNC_CLIENT = httpx.AsyncClient
QUERY = 'latest Raspberry Pi robot news'
RESULT_URL = 'https://www.raspberrypi.com/news/robotics/'


class McpServer:
    """An HTTP-level MCP fixture, including initialization and discovery."""

    def __init__(self, *, sse=False, text_only=False):
        self.requests = []
        self.calls = []
        self.sse = sse
        self.text_only = text_only
        self.error = None
        self.status = None
        self.delay_method = None
        self.cancel_bot = None
        self.results = [{
            'title': 'Robot news', 'url': RESULT_URL,
            'excerpts': ['A new robot uses a Raspberry Pi.'],
        }]
        self.delete_delay = 0

    async def handle(self, request):
        self.requests.append(request)
        # The live endpoint returns a session ID and supports session teardown.
        if request.method == 'GET':
            return httpx.Response(405)
        if request.method == 'DELETE':
            await asyncio.sleep(self.delete_delay)
            return httpx.Response(204)
        data = json.loads(request.content)
        method = data['method']
        if method == self.delay_method:
            await asyncio.sleep(5)
        if method == 'notifications/initialized':
            return httpx.Response(202)
        if method == 'initialize':
            result = {
                'protocolVersion': data['params']['protocolVersion'],
                'capabilities': {'tools': {}},
                'serverInfo': {'name': 'search-fixture', 'version': '1.0'},
            }
        elif method == 'tools/list':
            result = {'tools': [{
                'name': 'web_search', 'description': 'Search the web',
                'inputSchema': {'type': 'object', 'properties': {
                    'objective': {'type': 'string'},
                    'search_queries': {'type': 'array', 'items': {'type': 'string'}},
                    'session_id': {'type': 'string'},
                }, 'required': ['objective', 'search_queries']},
            }]}
        elif method == 'tools/call':
            self.calls.append(data['params'])
            if self.cancel_bot:
                asyncio.get_running_loop().call_later(
                    0.02, self.cancel_bot.handle_speaking_interrupt,
                )
                await asyncio.sleep(5)
            if self.status:
                return httpx.Response(self.status, json={'error': 'fixture quota'})
            if self.error:
                result = {'content': [{'type': 'text', 'text': self.error}], 'isError': True}
            else:
                response = {'search_id': 'fixture-search', 'results': self.results,
                            'session_id': data['params']['arguments']['session_id']}
                result = {'content': [{'type': 'text', 'text': json.dumps(response)}],
                          'isError': False}
                if not self.text_only:
                    result['structuredContent'] = response
            # Give concurrent conversations a chance to interleave.
            await asyncio.sleep(0.01)
        else:
            raise AssertionError('Unexpected MCP method: ' + method)
        envelope = {'jsonrpc': '2.0', 'id': data['id'], 'result': result}
        headers = {}
        if method == 'initialize':
            headers['mcp-session-id'] = str(uuid.uuid4())
        if self.sse:
            return httpx.Response(200, headers={**headers, 'content-type': 'text/event-stream'},
                                  text='event: message\ndata: ' + json.dumps(envelope) + '\n\n')
        return httpx.Response(200, headers=headers, json=envelope)

    def client(self, **kwargs):
        return REAL_ASYNC_CLIENT(transport=httpx.MockTransport(self.handle), **kwargs)


class AgentSearchTests(unittest.TestCase):
    def setUp(self):
        self.server = McpServer()
        self.config = patch.object(agent, 'CURRENT_CONFIG', {
            **agent.DEFAULT_CONFIG, 'search_provider': 'parallel',
            'search_timeout_seconds': 1,
        })
        self.config.start()
        self.client_patch = patch('httpx.AsyncClient', self.server.client)
        self.client_patch.start()
        self.ddgs = patch.object(agent, 'DDGS')
        self.duck = self.ddgs.start()
        self.addCleanup(self.config.stop)
        self.addCleanup(self.client_patch.stop)
        self.addCleanup(self.ddgs.stop)

    def make_bot(self):
        with patch.object(agent.BotGUI, 'load_animations'), \
                patch.object(agent.BotGUI, 'update_animation'), \
                patch.object(agent.BotGUI, 'load_chat_history', return_value=[
                    {'role': 'system', 'content': agent.SYSTEM_PROMPT},
                ]), patch('threading.Thread.start'), patch('atexit.register'):
            bot = agent.BotGUI(MagicMock())
        def state(value, *args, **kwargs):
            bot.current_state = value
        bot.set_state = Mock(side_effect=state)
        bot.append_to_text = Mock()
        bot._stream_to_text = Mock()
        bot.save_chat_history = Mock()
        bot.wait_for_tts = Mock()
        return bot

    def chat(self, bot, query=QUERY):
        summaries = []
        def reply(**kwargs):
            if kwargs['stream']:
                return iter([{'message': {'content': json.dumps({
                    'action': 'search_web', 'value': query,
                })}}])
            summaries.append(kwargs['messages'])
            return {'message': {'content': 'A new Raspberry Pi robot is in the news.'}}
        with patch.object(agent.ollama, 'chat', side_effect=reply), \
                patch.object(bot, '_run_thinking_sound_loop'):
            bot.chat_and_respond('Search for ' + query)
        return summaries

    def dispatch(self, bot, query=QUERY):
        return bot.execute_action_and_get_result({'action': 'search_web', 'query': query})

    def test_parallel_actual_chat_consumes_urls_and_excerpts_without_credentials(self):
        bot = self.make_bot()
        with patch.dict(os.environ, {'PARALLEL_API_KEY': 'unused-ambient-key'}):
            summary = self.chat(bot)
        self.assertEqual(len(summary), 1)
        self.assertIn(RESULT_URL, summary[0][1]['content'])
        self.assertIn('A new robot uses a Raspberry Pi.', summary[0][1]['content'])
        self.assertIn('A new Raspberry Pi robot', bot.session_memory[-1]['content'])
        self.assertEqual(bot.tts_queue, ['A new Raspberry Pi robot is in the news.'])
        self.assertEqual(self.server.calls[0]['name'], 'web_search')
        self.assertEqual(self.server.calls[0]['arguments'], {
            'objective': QUERY, 'search_queries': [QUERY],
            'session_id': bot.search_conversation.session_id,
        })
        self.assertEqual({json.loads(r.content)['method'] for r in self.server.requests if r.content},
                         {'initialize', 'notifications/initialized', 'tools/list', 'tools/call'})
        self.assertIn('DELETE', [r.method for r in self.server.requests])
        for request in self.server.requests:
            self.assertEqual(str(request.url), PARALLEL_MCP_URL)
            self.assertEqual(request.headers['user-agent'], USER_AGENT)
            self.assertNotIn('authorization', request.headers)
        self.duck.assert_not_called()

    def test_sse_and_text_content_responses(self):
        self.server.sse = True
        self.server.text_only = True
        self.assertIn(RESULT_URL, self.chat(self.make_bot())[0][1]['content'])

    def test_fresh_and_saved_duckduckgo_remain_news_first(self):
        bot = self.make_bot()
        for provider in (None, 'duckduckgo'):
            if provider is None:
                agent.CURRENT_CONFIG.pop('search_provider')
            else:
                agent.CURRENT_CONFIG['search_provider'] = provider
            context = self.duck.return_value.__enter__.return_value
            context.news.return_value = [{'title': 'Original news', 'body': 'Original snippet'}]
            result = self.dispatch(bot)
            self.assertIn('Original snippet', result)
            context.news.assert_called_with(QUERY, region='us-en', max_results=1)
            context.text.assert_not_called()
        self.assertFalse(self.server.requests)

    def test_duckduckgo_text_fallback_is_preserved(self):
        agent.CURRENT_CONFIG['search_provider'] = 'duckduckgo'
        context = self.duck.return_value.__enter__.return_value
        context.news.return_value = []
        context.text.return_value = [{'title': 'Text', 'body': 'Text fallback'}]
        self.assertIn('Text fallback', self.dispatch(self.make_bot()))
        context.text.assert_called_once_with(QUERY, region='us-en', max_results=1)

    def test_config_load_preserves_saved_provider_and_unrelated_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            with patch.object(agent, 'CONFIG_FILE', str(path)):
                self.assertEqual(agent.load_config()['search_provider'], 'duckduckgo')
                for provider in ('parallel', 'duckduckgo', 'disabled'):
                    original = json.dumps({'search_provider': provider, 'voice_model': 'custom.onnx'})
                    path.write_text(original)
                    loaded = agent.load_config()
                    self.assertEqual(loaded['search_provider'], provider)
                    self.assertEqual(loaded['voice_model'], 'custom.onnx')
                    self.assertEqual(path.read_text(), original)

    def test_disabled_and_invalid_selection_never_contact_a_provider(self):
        for provider in ('disabled', 'typo', None):
            agent.CURRENT_CONFIG['search_provider'] = provider
            bot = self.make_bot()
            self.assertEqual(self.chat(bot), [])
            if provider == 'disabled':
                self.assertEqual(bot.tts_queue, ['Web search is disabled in my settings.'])
        self.assertFalse(self.server.requests)
        self.duck.assert_not_called()

    def test_empty_query_never_contacts_a_provider(self):
        for query in (None, '', '  ', 123):
            self.assertEqual(self.dispatch(self.make_bot(), query), 'SEARCH_EMPTY')
        self.assertFalse(self.server.requests)

    def test_tool_error_and_http_quota_do_not_fallback_or_change_identity(self):
        bot = self.make_bot()
        identity = bot.search_conversation.session_id
        self.server.error = 'fixture service error'
        self.assertEqual(self.chat(bot), [])
        self.server.error = None
        self.server.status = 429
        self.assertEqual(self.dispatch(bot), 'SEARCH_ERROR')
        self.server.status = None
        self.assertIn(RESULT_URL, self.dispatch(bot))
        self.assertEqual([c['arguments']['session_id'] for c in self.server.calls], [identity] * 3)
        self.duck.assert_not_called()

    def test_timeout_bounds_initialize_discovery_and_tool_call(self):
        agent.CURRENT_CONFIG['search_timeout_seconds'] = 0.1
        for method in ('initialize', 'tools/list', 'tools/call'):
            self.server.delay_method = method
            bot = self.make_bot()
            started = time.monotonic()
            self.assertEqual(self.chat(bot), [])
            self.assertLess(time.monotonic() - started, 2)
        self.duck.assert_not_called()

    def test_interrupt_cancels_request_and_prevents_summary_and_speech(self):
        bot = self.make_bot()
        self.server.cancel_bot = bot
        started = time.monotonic()
        self.assertEqual(self.chat(bot), [])
        self.assertLess(time.monotonic() - started, 2)
        self.assertTrue(bot.interrupted.is_set())
        self.assertFalse(bot.thinking_sound_active.is_set())
        self.assertEqual(bot.tts_queue, [])
        self.duck.assert_not_called()

    def test_slow_stateful_teardown_cannot_extend_timeout_or_interruption(self):
        self.server.delete_delay = 0.6
        self.server.delay_method = 'tools/call'
        agent.CURRENT_CONFIG['search_timeout_seconds'] = 0.1
        started = time.monotonic()
        self.assertEqual(self.dispatch(self.make_bot()), 'SEARCH_ERROR')
        self.assertLess(time.monotonic() - started, 0.5)

        self.server.delay_method = None
        agent.CURRENT_CONFIG['search_timeout_seconds'] = 15
        bot = self.make_bot()
        self.server.cancel_bot = bot
        started = time.monotonic()
        self.assertEqual(self.chat(bot), [])
        self.assertLess(time.monotonic() - started, 0.5)
        self.assertEqual(bot.tts_queue, [])
        self.assertTrue(bot.interrupted.is_set())
        self.duck.assert_not_called()

    def test_already_interrupted_action_never_sends_network_request(self):
        bot = self.make_bot()
        bot.interrupted.set()
        self.assertEqual(self.dispatch(bot), 'SEARCH_CANCELLED')
        self.assertEqual(self.chat(bot), [])
        self.assertFalse(self.server.requests)

    def test_slow_os_dns_does_not_delay_timeout_or_interruption(self):
        def delayed_dns(*args, **kwargs):
            time.sleep(0.6)
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 443))]

        agent.CURRENT_CONFIG['search_timeout_seconds'] = 0.1
        bot = self.make_bot()
        # Keep the real HTTPX/MCP transport; only OS name resolution is delayed.
        # Cancellation completes before lookup returns, so no live search occurs.
        with patch('httpx.AsyncClient', REAL_ASYNC_CLIENT), \
                patch('socket.getaddrinfo', delayed_dns):
            started = time.monotonic()
            self.assertEqual(self.dispatch(bot), 'SEARCH_ERROR')
            self.assertLess(time.monotonic() - started, 0.5)

        agent.CURRENT_CONFIG['search_timeout_seconds'] = 15
        bot = self.make_bot()
        def interrupted_dns(*args, **kwargs):
            threading.Timer(0.02, bot.interrupted.set).start()
            return delayed_dns(*args, **kwargs)
        with patch('httpx.AsyncClient', REAL_ASYNC_CLIENT), \
                patch('socket.getaddrinfo', interrupted_dns):
            started = time.monotonic()
            self.assertEqual(self.dispatch(bot), 'SEARCH_CANCELLED')
            self.assertLess(time.monotonic() - started, 0.5)
        self.assertEqual(bot.tts_queue, [])
        self.duck.assert_not_called()

    def test_real_conversation_creation_followups_reset_and_interleaving(self):
        first, second = self.make_bot(), self.make_bot()
        first_id, second_id = first.search_conversation.session_id, second.search_conversation.session_id
        self.assertNotEqual(first_id, second_id)
        # These use the same resolver and HTTP fixture with separate GUI contexts.
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(self.dispatch, (first, second, first, second)))
        self.assertTrue(all(RESULT_URL in r for r in results))
        sent_ids = [c['arguments']['session_id'] for c in self.server.calls]
        self.assertEqual(sent_ids.count(first_id), 2)
        self.assertEqual(sent_ids.count(second_id), 2)
        for reset in ('reset memory', 'forget everything'):
            first.chat_and_respond(reset)
            new_id = first.search_conversation.session_id
            self.assertNotIn(new_id, (first_id, second_id))
            self.assertIn(RESULT_URL, self.dispatch(first))
            self.assertEqual(self.server.calls[-1]['arguments']['session_id'], new_id)
            first_id = new_id
        self.assertEqual(second.search_conversation.session_id, second_id)

    def test_invalid_timeout_fails_without_network(self):
        for timeout in (0, -1, 121, True, '15', None, float('nan'), float('inf')):
            agent.CURRENT_CONFIG['search_timeout_seconds'] = timeout
            self.assertEqual(self.dispatch(self.make_bot()), 'SEARCH_ERROR')
        self.assertFalse(self.server.requests)

    def test_missing_optional_sdk_fails_only_when_selected(self):
        with patch.dict(sys.modules, {'mcp': None}):
            self.assertEqual(self.dispatch(self.make_bot()), 'SEARCH_ERROR')
        self.duck.assert_not_called()

    def test_empty_malformed_and_unsafe_results_are_not_summarized(self):
        bot = self.make_bot()
        self.server.results = []
        self.assertEqual(self.dispatch(bot), 'SEARCH_EMPTY')
        for row in ({}, {'url': 'file:///etc/passwd', 'excerpts': ['bad']},
                    {'url': 'https://user:pass@example.com', 'excerpts': []},
                    {'url': 'https://example.com', 'excerpts': 'wrong'}):
            self.server.results = [row]
            self.assertEqual(self.chat(bot), [])
        self.duck.assert_not_called()

    def test_result_context_is_bounded_for_small_local_model(self):
        self.server.results = [{'url': RESULT_URL, 'title': 'a' * 500,
                                'excerpts': ['b' * 10000]}] * 10
        context = self.chat(self.make_bot())[0][1]['content']
        self.assertEqual(context.count('URL: '), 3)
        self.assertNotIn('a' * 161, context)
        self.assertNotIn('b' * 1001, context)


if __name__ == '__main__':
    unittest.main()
