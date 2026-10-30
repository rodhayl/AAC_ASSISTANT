"""Focused, offline tests for the historical snapshot's Cloud adapter patch."""
import os
import unittest
from unittest.mock import patch
import httpx
from src.aac_app.providers.ollama_provider import OllamaProvider

class CloudAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def close(self, provider):
        await provider.client.aclose()
        provider.sync_client.close()

    async def test_official_cloud_has_authorization(self):
        with patch.dict(os.environ, {'OLLAMA_API_KEY': 'synthetic-unit-key'}):
            p = OllamaProvider(base_url='https://ollama.com', model='beam:cloud')
        try:
            self.assertEqual(p.client.headers['Authorization'], 'Bearer synthetic-unit-key')
            self.assertEqual(p.sync_client.headers['Authorization'], 'Bearer synthetic-unit-key')
            self.assertFalse(p.client.follow_redirects)
        finally:
            await self.close(p)

    async def test_local_endpoint_never_receives_cloud_secret(self):
        with patch.dict(os.environ, {'OLLAMA_API_KEY': 'synthetic-unit-key'}):
            p = OllamaProvider(base_url='http://localhost:11434', model='synthetic')
        try:
            self.assertNotIn('Authorization', p.client.headers)
            self.assertNotIn('Authorization', p.sync_client.headers)
        finally:
            await self.close(p)

    async def test_cloud_requires_runtime_key(self):
        with patch.dict(os.environ, {'OLLAMA_API_KEY': ''}):
            with self.assertRaises(ValueError):
                OllamaProvider(base_url='https://ollama.com')

    async def test_rejects_noncanonical_official_endpoint(self):
        for url in ['http://ollama.com', 'https://ollama.com/other', 'https://user@ollama.com', 'https://ollama.com:443']:
            with self.subTest(url=url), patch.dict(os.environ, {'OLLAMA_API_KEY': 'synthetic-unit-key'}):
                with self.assertRaises(ValueError):
                    OllamaProvider(base_url=url)

    async def test_request_shape_and_error_body_redaction(self):
        with patch.dict(os.environ, {'OLLAMA_API_KEY': 'synthetic-unit-key'}):
            p = OllamaProvider(base_url='https://ollama.com', model='beam:cloud')
        await p.client.aclose()
        seen=[]
        def handler(request):
            seen.append(request)
            return httpx.Response(401, text='synthetic-sensitive-provider-detail')
        p.client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            with self.assertRaises(ConnectionError) as error:
                await p.generate('Synthetic unit prompt')
            self.assertNotIn('synthetic-sensitive-provider-detail', str(error.exception))
            self.assertEqual(seen[0].url.path, '/api/chat')
            self.assertIn(b'beam:cloud', seen[0].content)
        finally:
            await self.close(p)

if __name__ == '__main__':
    unittest.main()
