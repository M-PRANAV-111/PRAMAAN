import unittest

from app import schemas
from app.features import snapshot
from app.pipeline.hooks import STAGE_CODES, _steps, register_step, run_steps
from scripts.gen_contract import build_openapi


class SharedContractTests(unittest.TestCase):
    def test_defaults_preserve_existing_callers(self):
        self.assertEqual(schemas.DocumentOut.model_fields['version'].default, 1)
        self.assertIsNone(schemas.JobOut.model_fields['stage_code'].default)
        self.assertFalse(schemas.FindingOut.model_fields['ai_assisted'].default)
        self.assertIn('registration', snapshot())

    def test_stage_mapping_and_inert_ordered_hooks(self):
        self.assertTrue(set(STAGE_CODES.values()) <= set(schemas.StageCode.__args__))
        calls = []
        saved = list(_steps['after_fields'])
        try:
            _steps['after_fields'].clear()
            run_steps('after_fields', None, 'job', {}, None)
            self.assertEqual(calls, [])
            register_step('after_fields', lambda *args: calls.append(1))
            register_step('after_fields', lambda *args: calls.append(2))
            run_steps('after_fields', None, 'job', {}, None)
            self.assertEqual(calls, [1, 2])
        finally:
            _steps['after_fields'][:] = saved

    def test_contract_roles_and_pdf(self):
        paths = build_openapi()['paths']
        self.assertIn('application/pdf', paths['/api/v1/applications/{application_id}/report']['get']['responses']['200']['content'])
        self.assertEqual(len(paths['/api/v1/applications']['get']['parameters']), 4)
        self.assertIn('/api/v1/admin/registrations/{registration_id}/decline', paths)
        self.assertEqual(paths['/api/v1/metrics']['get']['security'], [{'metrics': []}])
        self.assertIn('X-Total-Count', paths['/api/v1/applications']['get']['responses']['200']['headers'])
        self.assertTrue(any(p['name'] == 'Idempotency-Key' for p in
                            paths['/api/v1/applications/{application_id}/documents']['post']['parameters']))
