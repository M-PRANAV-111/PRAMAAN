import os
import secrets
import unittest
from unittest.mock import patch

from app.config import Settings, _env_bool, get_settings, reset_settings_cache
from app.sessions import ip_hint, client_ip
from starlette.requests import Request


class ConfigurationTests(unittest.TestCase):
    def production(self,**overrides):
        return Settings(**{'env':'production','jwt_secret':secrets.token_urlsafe(40),'cookie_secure':True,
                           'public_base_url':'https://pramaan.example.test','email_provider':'smtp','smtp_host':'smtp.example.test',**overrides})

    def test_production_guards(self):
        for overrides in ({'email_provider':'console'},{'public_base_url':'http://example.test'},
                          {'demo_accounts':True},{'show_demo_accounts':True},{'cookie_secure':False},{'jwt_secret':'short'},{'cors_origins':['*']}):
            with self.subTest(overrides=overrides),self.assertRaises(ValueError):
                self.production(**overrides)
        with patch.dict(os.environ,{'SEED_DEMO_PASSWORD':''}):
            self.assertEqual(self.production().env,'production')

    def test_empty_values_and_proxy_defaults(self):
        with patch.dict(os.environ,{'TRUST_PROXY':'','FLY_APP_NAME':'synthetic-app','NOTIFY_EMAIL':'','SMTP_PORT':''}):
            reset_settings_cache()
            self.assertTrue(get_settings().trust_proxy)
            self.assertFalse(get_settings().notify_email)
            self.assertEqual(get_settings().smtp_port,587)
            self.assertTrue(_env_bool('TRUST_PROXY',True))
        reset_settings_cache()

    def test_ip_privacy_and_untrusted_forwarding(self):
        self.assertEqual(ip_hint('192.168.5.123'),'192.168.5.0/24')
        self.assertEqual(ip_hint('2001:db8:1234:5678::1'),'2001:db8:1234::/48')
        request=Request({'type':'http','headers':[(b'x-forwarded-for',b'1.2.3.4')],'client':('127.0.0.1',80)})
        with patch.dict(os.environ,{'TRUST_PROXY':'false'}):
            reset_settings_cache()
            self.assertEqual(client_ip(request),'127.0.0.1')
        with patch.dict(os.environ,{'TRUST_PROXY':'true'}):
            reset_settings_cache()
            self.assertEqual(client_ip(request),'1.2.3.4')
        reset_settings_cache()
