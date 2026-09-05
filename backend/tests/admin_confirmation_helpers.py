"""Issue real confirmation challenges while replacing only external SMTP delivery."""

from app.services import admin_confirmation_service


async def issue_confirmation(client, monkeypatch, headers, action, target_user_id, **parameters):
    delivered = []

    def capture_email(**mail):
        delivered.append(mail)
        return True

    monkeypatch.setattr(admin_confirmation_service, "send_admin_confirmation_email", capture_email)
    response = await client.post(
        "/api/v1/admin/reauth/challenges",
        headers=headers,
        json={"action": action, "target_user_id": target_user_id, **parameters},
    )
    assert response.status_code == 200, response.text
    return {"challenge_id": response.json()["challenge_id"], "code": delivered[-1]["code"]}
