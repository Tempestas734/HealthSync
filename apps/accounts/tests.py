import json
import uuid
from unittest.mock import MagicMock, patch

from django.test import RequestFactory, SimpleTestCase

from .forms import HealthProfessionalSessionCreateForm
from .views import _normalize_session_pin, activate_patient_exam_session, health_professional_session_lookup


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


class SessionPinNormalizationTests(SimpleTestCase):
    def test_normalizes_digits_only_pin(self):
        self.assertEqual(_normalize_session_pin(" 12-34 56 "), "123456")

    def test_rejects_invalid_pin_length(self):
        with self.assertRaisesMessage(ValueError, "exactement 6 chiffres"):
            _normalize_session_pin("12345")


class ActivatePatientExamSessionTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @patch("apps.accounts.views._db_table_exists", return_value=True)
    def test_requires_device_id(self, _mock_table_exists):
        request = self.factory.post(
            "/api/exam-sessions/activate/",
            data=json.dumps({"session_pin": "123456", "consent_id": str(uuid.uuid4())}),
            content_type="application/json",
        )

        response = activate_patient_exam_session(request)

        self.assertEqual(response.status_code, 400)
        self.assertIn("device_id", response.content.decode())

    @patch("apps.accounts.views._db_table_exists", return_value=True)
    def test_returns_not_found_when_session_pin_does_not_exist(self, _mock_table_exists):
        request = self.factory.post(
            "/api/exam-sessions/activate/",
            data=json.dumps(
                {
                    "session_pin": "123456",
                    "device_id": "kiosk-01",
                    "consent_id": str(uuid.uuid4()),
                }
            ),
            content_type="application/json",
        )

        with patch("apps.accounts.views.ExamSession.objects.select_related") as mock_select_related:
            mock_select_related.return_value.filter.return_value.order_by.return_value.first.return_value = None
            response = activate_patient_exam_session(request)

        self.assertEqual(response.status_code, 404)
        self.assertIn("Aucune session en attente", response.content.decode())

    @patch("apps.accounts.views.ExamSession.objects.select_related")
    @patch("apps.accounts.views._db_table_exists", return_value=True)
    def test_creates_patient_mode_session(
        self,
        _mock_table_exists,
        mock_session_select_related,
    ):
        patient_id = uuid.uuid4()
        consent_id = uuid.uuid4()

        session = MagicMock()
        session.id = uuid.uuid4()
        session.session_pin = "123456"
        session.status = "pending"
        session.mode = "patient"
        session.patient_id = patient_id
        mock_session_select_related.return_value.filter.return_value.order_by.return_value.first.return_value = session

        request = self.factory.post(
            "/api/exam-sessions/activate/",
            data=json.dumps(
                {
                    "session_pin": "123456",
                    "device_id": "kiosk-01",
                    "consent_id": str(consent_id),
                    "rfid_tag_uid": "RFID-001",
                }
            ),
            content_type="application/json",
        )

        response = activate_patient_exam_session(request)

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["mode"], "patient")
        self.assertEqual(payload["session_pin"], "123456")
        self.assertEqual(session.device_id, "kiosk-01")
        self.assertEqual(session.consent_id, consent_id)
        self.assertEqual(session.rfid_tag_uid, "RFID-001")
        self.assertEqual(session.status, "active")
        session.save.assert_called_once_with(update_fields=["device_id", "consent_id", "rfid_tag_uid", "status"])


class HealthProfessionalSessionLookupTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @patch("apps.accounts.views.render")
    @patch("apps.accounts.views.ExamSession.objects.create")
    @patch("apps.accounts.views.Patient.objects.select_related")
    @patch("apps.accounts.views._generate_unique_session_pin", return_value="123456")
    @patch("apps.accounts.views._db_table_exists", return_value=True)
    def test_created_session_uses_authenticated_user_id(
        self,
        _mock_table_exists,
        _mock_generate_pin,
        mock_patient_select_related,
        mock_create_session,
        mock_render,
    ):
        patient = MagicMock()
        patient.user_id = uuid.uuid4()
        mock_patient_select_related.return_value.filter.return_value.order_by.return_value.first.return_value = patient

        request = self.factory.post(
            "/health-professional/session/",
            data={"patient_code": "PAT-001"},
        )
        request.session = {"user_id": str(uuid.uuid4())}

        health_professional_session_lookup(request)

        self.assertTrue(mock_create_session.called)
        self.assertEqual(mock_create_session.call_args.kwargs["user_id"], request.session["user_id"])
