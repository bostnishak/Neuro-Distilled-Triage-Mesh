import asyncio
import datetime
import uuid
from sqlalchemy import text
from core.config import settings
from core.logging_otel import logger
from core.security_ed25519_jwt import hash_password, global_signer
from infrastructure.database.connection import engine, AsyncSessionLocal
from infrastructure.repositories.uow_repositories import UnitOfWork
from domain.services.merkle_audit_ledger import MerkleAuditLedger
from infrastructure.database.orm_models import MerkleAuditBlockOrm, UserOrm


async def bootstrap_genesis() -> None:
    """NDTM-9000 Sovereign Kernel Genesis Bootstrapper."""
    logger.info("ndtm_genesis_bootstrap_initiating", service=settings.SERVICE_NAME)

    # 1. Verify PostgreSQL & Extensions
    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT extname FROM pg_extension WHERE extname IN ('postgis', 'vector')"))
        exts = [r[0] for r in res.fetchall()]
        logger.info("database_extensions_verified", installed=exts)

    # 2. Seed Default Admin User if missing
    async with AsyncSessionLocal() as session:
        async with UnitOfWork(session) as uow:
            res = await uow.session.execute(text("SELECT id FROM users WHERE email = 'admin@ndtm.sovereign'"))
            existing_admin = res.scalar_one_or_none()

            if not existing_admin:
                admin_user = UserOrm(
                    id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
                    email="admin@ndtm.sovereign",
                    password_hash=hash_password("AdminSovereign2026!MasterKey"),
                    full_name="Chief Sovereign Architect",
                    role="ADMIN",
                    is_active=True,
                )
                uow.session.add(admin_user)
                await uow.session.flush()
                logger.info("genesis_admin_user_created", email="admin@ndtm.sovereign")

            # 3. Check / Seal Genesis Block (Height 0)
            res_block = await uow.session.execute(text("SELECT height FROM merkle_audit_blocks WHERE height = 0"))
            existing_block = res_block.scalar_one_or_none()

            if not existing_block:
                genesis_parent = "0" * 64
                genesis_root = MerkleAuditLedger.build_merkle_root([]).digest
                now = datetime.datetime.now(datetime.timezone.utc)
                genesis_hash = MerkleAuditLedger.compute_block_hash(
                    genesis_parent, genesis_root, 0, now.isoformat(), 0
                )
                sig = global_signer.sign_hex(bytes.fromhex(genesis_hash.digest))

                genesis_block = MerkleAuditBlockOrm(
                    height=0,
                    block_hash=genesis_hash.digest,
                    parent_hash=genesis_parent,
                    merkle_root=genesis_root,
                    events_count=0,
                    sealed_at=now,
                    kernel_signature_hex=sig,
                    state_commit_proof={"status": "GENESIS_INITIALIZED", "system": "NDTM-9000"},
                )
                uow.session.add(genesis_block)
                logger.info("genesis_merkle_block_0_sealed", block_hash=genesis_hash.digest[:16])

    logger.info("ndtm_genesis_bootstrap_successfully_completed")


if __name__ == "__main__":
    asyncio.run(bootstrap_genesis())
