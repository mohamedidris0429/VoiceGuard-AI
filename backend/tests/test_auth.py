"""Authentication and account tests."""

from __future__ import annotations


def test_register_creates_account_and_returns_token(client):
    response = client.post(
        "/api/auth/register",
        json={"name": "Ada Lovelace", "email": "Ada@Example.com", "password": "Str0ngPass123"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["email"] == "ada@example.com"
    assert "password" not in body["user"]
    assert "password_hash" not in body["user"]


def test_duplicate_email_rejected(client, register_user):
    user = register_user()
    response = client.post(
        "/api/auth/register",
        json={"name": "Copy Cat", "email": user["email_used"], "password": "Str0ngPass123"},
    )
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"].lower()


def test_weak_password_rejected(client):
    response = client.post(
        "/api/auth/register",
        json={"name": "Weak Pass", "email": "weak@example.com", "password": "short"},
    )
    assert response.status_code == 422


def test_invalid_email_rejected(client):
    response = client.post(
        "/api/auth/register",
        json={"name": "Bad Email", "email": "not-an-email", "password": "Str0ngPass123"},
    )
    assert response.status_code == 422


def test_login_success(client, register_user):
    user = register_user()
    response = client.post(
        "/api/auth/login",
        json={"email": user["email_used"], "password": user["password"]},
    )
    assert response.status_code == 200
    assert response.json()["access_token"]


def test_login_invalid_password(client, register_user):
    user = register_user()
    response = client.post(
        "/api/auth/login",
        json={"email": user["email_used"], "password": "WrongPass123"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."


def test_login_unknown_email(client):
    response = client.post(
        "/api/auth/login",
        json={"email": "ghost@example.com", "password": "Str0ngPass123"},
    )
    assert response.status_code == 401


def test_me_requires_authentication(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_me_rejects_invalid_token(client):
    response = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401


def test_me_returns_current_user(client, register_user, auth_headers):
    user = register_user(name="Grace Hopper")
    response = client.get("/api/auth/me", headers=auth_headers(user))
    assert response.status_code == 200
    assert response.json()["name"] == "Grace Hopper"


def test_update_profile(client, register_user, auth_headers):
    user = register_user()
    response = client.patch(
        "/api/auth/me",
        json={"name": "Renamed User", "preferences": {"default_view": "history", "bogus": 1}},
        headers=auth_headers(user),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Renamed User"
    assert body["preferences"] == {"default_view": "history"}


def test_change_password_flow(client, register_user, auth_headers):
    user = register_user()
    headers = auth_headers(user)

    wrong = client.post(
        "/api/auth/change-password",
        json={"current_password": "Nope12345", "new_password": "N3wStrongPass"},
        headers=headers,
    )
    assert wrong.status_code == 401

    ok = client.post(
        "/api/auth/change-password",
        json={"current_password": user["password"], "new_password": "N3wStrongPass"},
        headers=headers,
    )
    assert ok.status_code == 200

    old_login = client.post(
        "/api/auth/login", json={"email": user["email_used"], "password": user["password"]}
    )
    assert old_login.status_code == 401

    new_login = client.post(
        "/api/auth/login", json={"email": user["email_used"], "password": "N3wStrongPass"}
    )
    assert new_login.status_code == 200


def test_password_is_hashed_in_database(client, register_user):
    from sqlalchemy import select

    from app.database.session import SessionLocal
    from app.models.user import User

    user = register_user()
    with SessionLocal() as session:
        stored = session.scalar(select(User).where(User.email == user["email_used"]))
    assert stored is not None
    assert stored.password_hash != user["password"]
    assert stored.password_hash.startswith("$2")
