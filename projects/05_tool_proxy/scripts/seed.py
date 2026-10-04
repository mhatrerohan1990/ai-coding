import hashlib
import secrets

from app.db import Base, SessionLocal, engine
from app.models import (
    Agent,
    Tenant,
    TenantAgentAccess,
    Tool,
    ToolAccess,
    User,
    UserRole,
)


def make_credential() -> tuple[str, str, str]:
    prefix = secrets.token_hex(4)
    secret = secrets.token_urlsafe(24)
    return f"{prefix}.{secret}", prefix, hashlib.sha256(secret.encode()).hexdigest()


def seed() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    with SessionLocal() as db:
        acme = Tenant(name="acme", ai_enabled=True)
        globex = Tenant(name="globex", ai_enabled=False)
        db.add_all([acme, globex])

        list_users = Tool(name="list_users")
        export_users = Tool(name="export_users")
        disable_user = Tool(name="disable_user")
        db.add_all([list_users, export_users, disable_user])

        db.flush()

        users = {
            "alice": User(name="alice", tenant_id=acme.id, role=UserRole.ADMIN),
            "bob": User(name="bob", tenant_id=acme.id, role=UserRole.MEMBER),
            "carol": User(name="carol", tenant_id=acme.id, enabled=False),
            "dave": User(name="dave", tenant_id=globex.id),
        }
        db.add_all(users.values())

        assistant = Agent(name="assistant")
        db.add(assistant)
        db.flush()

        db.add_all(
            [
                ToolAccess(user_id=users["alice"].id, tool_id=list_users.id, agent_id=assistant.id),
                ToolAccess(user_id=users["alice"].id, tool_id=export_users.id, agent_id=assistant.id),
                ToolAccess(user_id=users["alice"].id, tool_id=disable_user.id, agent_id=assistant.id),
                ToolAccess(user_id=users["bob"].id, tool_id=list_users.id, agent_id=assistant.id),
                ToolAccess(user_id=users["carol"].id, tool_id=list_users.id, agent_id=assistant.id),
                ToolAccess(user_id=users["dave"].id, tool_id=list_users.id, agent_id=assistant.id),
            ]
        )

        creds = {}
        for tenant in (acme, globex):
            token, prefix, hashed = make_credential()
            creds[tenant.name] = token
            db.add(
                TenantAgentAccess(
                    tenant_id=tenant.id,
                    agent_id=assistant.id,
                    secret_prefix=prefix,
                    secret_hash=hashed,
                )
            )

        tenant_ids = {t.name: t.id for t in (acme, globex)}
        user_ids = {name: u.id for name, u in users.items()}
        db.commit()

    print("Tenants:")
    for name, tenant_id in tenant_ids.items():
        print(f"  {name}: {tenant_id}")
    print("Users:")
    for name, user_id in user_ids.items():
        print(f"  {name}: {user_id}")
    print("Agent credentials (shown once):")
    for tenant_name, token in creds.items():
        print(f"  {tenant_name}: {token}")


if __name__ == "__main__":
    seed()
