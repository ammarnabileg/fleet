"""GPS points are kept as long as the client decides (a setting, months before the current one; 0 keeps them all):
the daily task deletes whole older months and says so in the audit log, never a month still kept."""

from datetime import date

from sqlalchemy import text

from app.core.clock import utcnow


def months(db) -> set[str]:
    return {
        n
        for (n,) in db.execute(
            text(
                "SELECT c.relname FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid "
                "WHERE i.inhparent = 'tracking.positions'::regclass"
            )
        )
    }


def back(n: int) -> date:
    t = utcnow()
    index = t.year * 12 + t.month - 1 - n
    return date(index // 12, index % 12 + 1, 1)


def test_old_months_go_only_with_a_retention_and_never_the_kept_ones(admin_client, db):
    from app.modules.tracking import service

    for n in (14, 3, 2):
        db.execute(text("SELECT tracking.ensure_month_partition(:m)"), {"m": back(n)})
    db.commit()
    name = lambda n: f"positions_{back(n):%Y_%m}"  # noqa: E731
    assert service.maintain_partitions(db) == 0  # the default keeps everything
    assert {name(14), name(3), name(2)} <= months(db)

    current = admin_client.get("/api/v1/settings").json()["tracking"]
    r = admin_client.put(
        "/api/v1/settings/tracking",
        json={"version": current["version"], "value": current["value"] | {"retention_months": 2}},
    )
    assert r.status_code == 200, r.text
    assert service.maintain_partitions(db) == 2  # 14 and 3 months back; the two before this one stay
    left = months(db)
    assert name(14) not in left and name(3) not in left and name(2) in left and f"positions_{back(0):%Y_%m}" in left
    [event] = admin_client.get("/api/v1/audit", params={"action": "tracking.points_deleted"}).json()
    assert (event["actor_type"], event["after"]["months"], event["after"]["retention_months"]) == ("system", 2, 2)
    assert service.maintain_partitions(db) == 0  # nothing more the next day
