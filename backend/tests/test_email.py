from unittest.mock import patch, MagicMock

from app import email
from app.config import get_settings
from app.db import reader
from tests.local_support import LocalDatabaseCase


class EmailTests(LocalDatabaseCase):
    def test_provider_retries_and_sanitized_failure_metric(self):
        with patch.object(email,'_deliver',side_effect=email.DeliveryError('http_503')) as delivery, \
             patch.object(email.time,'sleep'):
            email.send_email('synthetic@example.test','PRAMAAN synthetic test','Private synthetic body')
            email.drain()
        self.assertEqual(delivery.call_count,3)
        with reader() as c:
            rows=c.execute('SELECT * FROM email_failures').fetchall()
        self.assertEqual(len(rows),3)
        self.assertTrue(all(r['error_code']=='http_503' for r in rows))
        self.assertNotIn('Private synthetic',str([tuple(r) for r in rows]))

    def test_smtp_uses_starttls_and_resend_has_bounded_https_request(self):
        s=get_settings()
        s.email_provider='smtp'
        s.smtp_host='smtp.example.test'
        with patch.object(email.smtplib,'SMTP') as smtp:
            email._deliver('synthetic@example.test','PRAMAAN test','Synthetic body',None)
            smtp.return_value.__enter__.return_value.starttls.assert_called_once()
            smtp.return_value.__enter__.return_value.send_message.assert_called_once()
        s.email_provider='resend'
        s.resend_api_key='synthetic-provider-test-only'
        with patch.object(email.requests,'post',return_value=MagicMock(status_code=200)) as post:
            email._deliver('synthetic@example.test','PRAMAAN test','Synthetic body',None)
        self.assertEqual(post.call_args.args[0],'https://api.resend.com/emails')
        self.assertFalse(post.call_args.kwargs['allow_redirects'])
        self.assertEqual(post.call_args.kwargs['timeout'],20)
        self.assertIn('PRAMAAN prototype',post.call_args.kwargs['json']['text'])
