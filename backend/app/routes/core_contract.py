"""Temporary shared-contract handlers, replaced by feature modules in the next changeset."""
from ..api import ApiError, route
from .. import schemas as s


def stub(name, method, path, response, body=None, roles=None, public=False, status=200, raw=False, query=None):
    def handler(ctx):
        raise ApiError(501, "not_implemented", "This feature is not available yet")
    handler.__name__ = name
    route(method, "/api/v1" + path, summary=name.replace("_", " ").capitalize(), tag="accounts",
          response=response, body=body, roles=roles, public=public, status=status, raw=raw, query=query)(handler)


stub("register", "POST", "/auth/register", s.AcceptedOut, s.RegisterRequest, public=True, status=202)
stub("verify_email", "POST", "/auth/verify-email", s.OkOut, s.TokenRequest, public=True)
stub("accept_invitation", "POST", "/auth/accept-invitation", s.OkOut, s.AcceptInvitationRequest, public=True)
stub("forgot_password", "POST", "/auth/password/forgot", s.AcceptedOut, s.EmailRequest, public=True, status=202)
stub("reset_password", "POST", "/auth/password/reset", s.OkOut, s.PasswordResetRequest, public=True)
stub("change_password", "POST", "/auth/password/change", s.OkOut, s.PasswordChangeRequest)
stub("refresh", "POST", "/auth/refresh", s.SessionOut)
stub("get_account", "GET", "/account", s.AccountOut)
stub("update_account", "PATCH", "/account", s.AccountOut, s.AccountUpdate)
stub("list_sessions", "GET", "/account/sessions", list[s.SessionInfoOut])
stub("revoke_session", "DELETE", "/account/sessions/{session_id}", s.OkOut)
stub("revoke_other_sessions", "POST", "/account/sessions/revoke-others", s.OkOut)
stub("list_notifications", "GET", "/notifications", list[s.NotificationOut], query={"unread": "Only unread", "limit": "Up to 200", "offset": "Offset"})
stub("unread_count", "GET", "/notifications/unread-count", s.CountOut)
stub("read_notification", "POST", "/notifications/{notification_id}/read", s.OkOut)
stub("read_all_notifications", "POST", "/notifications/read-all", s.OkOut)
stub("application_timeline", "GET", "/applications/{application_id}/timeline", list[s.TimelineEventOut])
stub("application_report", "GET", "/applications/{application_id}/report", None, raw="application/pdf")
stub("document_history", "GET", "/applications/{application_id}/documents/history", list[s.DocumentOut])
stub("respond_to_finding", "POST", "/findings/{finding_id}/responses", s.ResponseOut, s.ResponseRequest, roles=("INSTITUTION",))
stub("list_registrations", "GET", "/admin/registrations", list[s.RegistrationOut], roles=("ADMIN",), query={"status": "Registration status"})
stub("accept_registration", "POST", "/admin/registrations/{registration_id}/accept", s.RegistrationOut, s.AcceptRegistrationRequest, roles=("ADMIN",))
stub("decline_registration", "POST", "/admin/registrations/{registration_id}/decline", s.RegistrationOut, s.ReasonRequest, roles=("ADMIN",))
stub("list_users", "GET", "/admin/users", list[s.AdminUserOut], roles=("ADMIN",), query={"role": "Role", "active": "Active accounts"})
stub("invite_user", "POST", "/admin/invitations", s.AcceptedOut, s.InvitationRequest, roles=("ADMIN",), status=202)
stub("deactivate_user", "POST", "/admin/users/{user_id}/deactivate", s.AdminUserOut, s.ReasonRequest, roles=("ADMIN",))
stub("reactivate_user", "POST", "/admin/users/{user_id}/reactivate", s.AdminUserOut, roles=("ADMIN",))
stub("system_status", "GET", "/admin/system", s.SystemOut, roles=("ADMIN", "AUDITOR"))
