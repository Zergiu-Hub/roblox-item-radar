import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("DISCORD_WEBHOOK", "https://example.invalid/test")
os.environ.setdefault("DEALS_DISCORD_WEBHOOK", "https://example.invalid/test")
import monitor
import deals
import requests


class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = Path.cwd()
        os.chdir(self.temp.name)
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.output.__enter__()

    def tearDown(self):
        self.output.__exit__(None, None, None)
        os.chdir(self.old)
        self.temp.cleanup()

    def test_failed_catalog_fails_both_runs(self):
        for module, getter in [(monitor, 'get_catalog_items'), (deals, 'get_collectibles')]:
            with self.subTest(module=module.__name__), patch.object(module, getter, return_value=None):
                with self.assertRaisesRegex(RuntimeError, 'catalog check failed'):
                    module.main()

    def check_delivery(self, module, getter, state_file, queue, state, item):
        Path(state_file).write_text(json.dumps(state))
        with patch.object(module, getter, return_value=[item]), patch.object(monitor, 'get_thumbnails', return_value={}), patch.object(deals, 'get_thumbnail', return_value=None), patch('alert_delivery.requests.post', side_effect=requests.ConnectionError('unavailable')):
            with self.assertRaisesRegex(RuntimeError, 'pending delivery'):
                module.main()
        self.assertEqual(len(json.loads(Path(queue).read_text())), 1)
        # Retry after restart even if the item disappears from the catalog.
        with patch.object(module, getter, return_value=[]), patch('alert_delivery.requests.post', return_value=Mock()) as post:
            module.main()
        self.assertEqual(post.call_count, 1)
        self.assertEqual(json.loads(Path(queue).read_text()), {})
        # Successful messages must not be sent again on the next run.
        with patch.object(module, getter, return_value=[]), patch('alert_delivery.requests.post') as post:
            module.main()
        post.assert_not_called()

    def test_item_alert_survives_failed_delivery(self):
        self.check_delivery(monitor, 'get_catalog_items', 'seen_items.json', 'pending_items.json', {'1': {'price': 100}}, {'id': 2, 'name': 'Free item', 'price': 0, 'creatorTargetId': 1})

    def test_deal_alert_survives_failed_delivery(self):
        self.check_delivery(deals, 'get_collectibles', 'deals_state.json', 'pending_deals.json', {'2': {'lowest_price': 100}}, {'id': 2, 'name': 'Limited', 'lowestPrice': 80})

    def test_rate_limit_retains_message(self):
        from alert_delivery import AlertDelivery
        delivery = AlertDelivery('https://example.invalid/test', 'queue.json')
        response = Mock()
        response.raise_for_status.side_effect = requests.HTTPError('429')
        with patch('alert_delivery.requests.post', return_value=response):
            self.assertFalse(delivery.send({'title': 'Test'}))
        self.assertEqual(len(json.loads(Path('queue.json').read_text())), 1)


if __name__ == '__main__':
    unittest.main()
