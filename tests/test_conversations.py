"""Tests for conversation CRUD endpoints."""

import pytest

from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_list_conversations_empty(initialized_client):
    resp = await initialized_client.get("/conversations", headers=auth_headers())
    assert resp.status_code == 200
    assert resp.json() == {"conversations": []}


@pytest.mark.asyncio
async def test_create_conversation(initialized_client):
    resp = await initialized_client.post(
        "/conversations",
        json={"title": "Test convo"},
        headers=auth_headers(),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Test convo"
    assert "id" in data
    assert "created_at" in data


@pytest.mark.asyncio
async def test_list_conversations_after_create(initialized_client):
    headers = auth_headers()
    await initialized_client.post("/conversations", json={"title": "One"}, headers=headers)
    await initialized_client.post("/conversations", json={"title": "Two"}, headers=headers)

    resp = await initialized_client.get("/conversations", headers=headers)
    assert resp.status_code == 200
    convos = resp.json()["conversations"]
    assert len(convos) == 2


@pytest.mark.asyncio
async def test_delete_conversation(initialized_client):
    headers = auth_headers()
    create_resp = await initialized_client.post(
        "/conversations", json={"title": "To delete"}, headers=headers
    )
    conv_id = create_resp.json()["id"]

    del_resp = await initialized_client.delete(f"/conversations/{conv_id}", headers=headers)
    assert del_resp.status_code == 200
    assert del_resp.json() == {"deleted": True}

    # Verify it's gone
    list_resp = await initialized_client.get("/conversations", headers=headers)
    assert len(list_resp.json()["conversations"]) == 0


@pytest.mark.asyncio
async def test_delete_nonexistent_conversation(initialized_client):
    resp = await initialized_client.delete("/conversations/nonexistent-id", headers=auth_headers())
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_messages_empty(initialized_client):
    headers = auth_headers()
    create_resp = await initialized_client.post(
        "/conversations", json={"title": "Msgs test"}, headers=headers
    )
    conv_id = create_resp.json()["id"]

    resp = await initialized_client.get(f"/conversations/{conv_id}/messages", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"messages": []}


@pytest.mark.asyncio
async def test_conversations_require_auth(initialized_client):
    resp = await initialized_client.get("/conversations")
    assert resp.status_code == 401
