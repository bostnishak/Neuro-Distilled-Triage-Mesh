import asyncio
import uuid
from sqlalchemy import select
from infrastructure.database.connection import AsyncSessionLocal
from infrastructure.database.orm_models import HitlApprovalRequestOrm

async def seed_hitl():
    async with AsyncSessionLocal() as session:
        check = await session.execute(
            select(HitlApprovalRequestOrm).where(HitlApprovalRequestOrm.status == "PENDING")
        )
        existing = check.scalars().all()
        if len(existing) > 0:
            print(f"Already seeded: {len(existing)} pending HITL requests")
            return

        req1 = HitlApprovalRequestOrm(
            id=uuid.UUID("20000000-0000-0000-0000-000000000001"),
            incident_id=uuid.UUID("9fbb44e8-2a8a-4e73-8e56-129f924bfe26"),
            proposed_action="ISOLATE_SUBSTATION_GRID_FEEDER_4",
            requires_role="INCIDENT_COMMANDER",
            status="PENDING",
            justification_evidence={
                "telemetry": "SCADA_AYEDAS_TEIAS_GW02",
                "core_temp_c": 118.4,
                "runaway_risk": 0.94,
                "affected_population": 42000,
                "recommended_reroute": "MODA_RING_FEEDER_2"
            }
        )

        req2 = HitlApprovalRequestOrm(
            id=uuid.UUID("20000000-0000-0000-0000-000000000002"),
            incident_id=uuid.UUID("8e4a58e7-a789-46c2-b519-8440ccff6ccc"),
            proposed_action="TRIGGER_SECTOR_VALVE_EMERGENCY_SHUTDOWN",
            requires_role="ARCHITECT",
            status="PENDING",
            justification_evidence={
                "gas_ppm": 450,
                "lel_pct": 38.5,
                "wind": "NE_18KMH",
                "evacuation_radius_m": 350,
                "sms_broadcast_queued": True
            }
        )

        session.add(req1)
        session.add(req2)
        await session.commit()
        print("Successfully seeded 2 pending HITL approval requests via ORM!")

if __name__ == "__main__":
    asyncio.run(seed_hitl())
