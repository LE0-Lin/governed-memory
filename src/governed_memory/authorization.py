"""OpenFGA REST checks intersect the ledger's local grants and source audiences."""

import base64
import re
from dataclasses import replace
from urllib.parse import urlsplit

import httpx

from governed_memory.errors import Denied


def user_key(principal_id):
    # Principal names cannot inject an OpenFGA type, userset or wildcard.
    encoded = base64.urlsafe_b64encode(principal_id.encode()).decode().rstrip("=")
    return f"user:{encoded}"


def authorization_model():
    relations = {"admin": {"this": {}}}
    for relation, inherited in (
        ("approver", "admin"),
        ("writer", "approver"),
        ("reader", "writer"),
    ):
        relations[relation] = {
            "union": {
                "child": [
                    {"this": {}},
                    {"computedUserset": {"relation": inherited}},
                ]
            }
        }
    return {
        "schema_version": "1.1",
        "type_definitions": [
            {"type": "user"},
            {
                "type": "project",
                "relations": relations,
                "metadata": {
                    "relations": {
                        relation: {"directly_related_user_types": [{"type": "user"}]}
                        for relation in relations
                    }
                },
            },
        ],
    }


def connection(endpoint, api_key=None):
    parsed = urlsplit(endpoint)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or (parsed.username or parsed.password or parsed.query or parsed.fragment)
    ):
        raise ValueError("OpenFGA URL must be an absolute HTTP(S) service URL")
    return httpx.Client(
        base_url=endpoint.rstrip("/") + "/",
        timeout=5,
        follow_redirects=False,
        headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
    )


class OpenFgaAuthorizer:
    def __init__(self, endpoint, store_id, model_id, *, api_key=None):
        if not all(
            re.fullmatch(r"[0-9A-HJKMNP-TV-Z]{26}", value) for value in (store_id, model_id)
        ):
            raise ValueError("OpenFGA store and model IDs must be pinned ULIDs")
        self.endpoint, self.store_id, self.model_id, self.api_key = (
            endpoint,
            store_id,
            model_id,
            api_key,
        )
        # Validate even before the first request; credentials are not logged or persisted.
        with connection(endpoint, api_key):
            pass

    def allows(self, identity, relation):
        if relation not in {"reader", "writer", "approver", "admin"}:
            raise ValueError("unknown authorization relation")
        try:
            with connection(self.endpoint, self.api_key) as client:
                response = client.post(
                    f"stores/{self.store_id}/check",
                    json={
                        "authorization_model_id": self.model_id,
                        "tuple_key": {
                            "user": user_key(identity.id),
                            "relation": relation,
                            "object": f"project:{identity.project}",
                        },
                        "consistency": "HIGHER_CONSISTENCY",
                    },
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict) or type(payload.get("allowed")) is not bool:
                    raise Denied("OpenFGA returned an invalid authorization decision")
                return payload["allowed"]
        except (httpx.HTTPError, ValueError) as exc:
            raise Denied("OpenFGA authorization unavailable") from exc

    def check(self, identity, relation):
        if not self.allows(identity, relation):
            raise Denied("OpenFGA permission denied")

    def restrict(self, identity):
        roles = ("reader", "agent", "approver", "admin")
        for role in reversed(roles[: roles.index(identity.role) + 1]):
            if self.allows(identity, "writer" if role == "agent" else role):
                return replace(identity, role=role)
        raise Denied("OpenFGA permission denied")

    def grant(self, principal_id, project, role, *, remove=False):
        """Operator-only relationship administration; call after an admin check."""
        relation = "writer" if role == "agent" else role
        if relation not in {"reader", "writer", "approver", "admin"}:
            raise ValueError("unknown authorization role")
        with connection(self.endpoint, self.api_key) as client:
            response = client.post(
                f"stores/{self.store_id}/write",
                json={
                    "authorization_model_id": self.model_id,
                    "deletes" if remove else "writes": {
                        "tuple_keys": [
                            {
                                "user": user_key(principal_id),
                                "relation": relation,
                                "object": f"project:{project}",
                            }
                        ]
                    },
                },
            )
            response.raise_for_status()


def provision(endpoint, project, grants, *, api_key=None):
    """Bootstrap a dedicated store from a locally authenticated operator's project grants."""
    with connection(endpoint, api_key) as client:
        response = client.post("stores", json={"name": f"governed-memory-{project}"})
        response.raise_for_status()
        store_id = response.json()["id"]
        response = client.post(
            f"stores/{store_id}/authorization-models", json=authorization_model()
        )
        response.raise_for_status()
        model_id = response.json()["authorization_model_id"]
    authorizer = OpenFgaAuthorizer(endpoint, store_id, model_id, api_key=api_key)
    for principal_id, role in grants:
        authorizer.grant(principal_id, project, role)
    return authorizer
