from django.test import SimpleTestCase

from .forms import HealthProfessionalSessionCreateForm


class HealthProfessionalSessionCreateFormTests(SimpleTestCase):
    def test_accepts_patient_code(self):
        form = HealthProfessionalSessionCreateForm(data={"patient_code": "PAT-001"})

        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["patient_code"], "PAT-001")

    def test_normalizes_case(self):
        form = HealthProfessionalSessionCreateForm(data={"patient_code": "pat-001"})

        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["patient_code"], "PAT-001")

    def test_rejects_empty_patient_code(self):
        form = HealthProfessionalSessionCreateForm(data={"patient_code": "   "})

        self.assertFalse(form.is_valid())
        self.assertIn("obligatoire", form.errors["patient_code"][0])
