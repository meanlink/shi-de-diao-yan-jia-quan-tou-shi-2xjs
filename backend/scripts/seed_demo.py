import time, json
from datetime import date, timedelta
from sqlalchemy import select, func
from src.config.database import Session
from migrations.initial import migrate
from src.models import User, Dataset, Volume, Job, Report, Delivery, Audit
from src.services.business import metadata, seed_records, analyze_volume
from src.services import jobs as job_service
from src.services.reports import deliver
from src.utils.security import hash_password
from src.utils.serialization import checksum


def _seed_volumes(db, admin, m):
    rows = seed_records()
    dataset = db.scalar(select(Dataset).where(Dataset.name == m['dataset_name']))

    def build(name, series, sequence, records, exclusions=()):
        volume = db.scalar(select(Volume).where(Volume.name == name))
        if volume:
            return volume, False
        volume = Volume(name=name, series=series, sequence=sequence,
                        dataset_id=dataset.id if dataset else None,
                        source=m['short'] + '-202611.csv', records=records,
                        exclusions=list(exclusions), status='collecting',
                        created_by=admin.id, created_at=time.time() - 3600)
        db.add(volume)
        db.flush()
        return volume, True

    # 第1卷：30天全部配齐，已封卷并完成计算，作为基线。
    first, created = build('南岭日表 · 第1卷', '南岭日表', 1, rows)
    if created:
        from src.services.business import window_report
        assert not window_report(rows, [])['pending']
        first.status = 'sealed'
        first.sealed_at = time.time() - 3500
        first.sealed_by = admin.email
        params = {p['key']: p['default'] for p in m.get('parameters', [])}
        job = job_service.create_for_volume(db, first, params, admin)
        result = analyze_volume(first.records, first.exclusions, params)
        json.dumps(result, ensure_ascii=False, allow_nan=False)
        job.status = 'completed'
        job.result = result
        job.approved = True
        job.finished_at = time.time() - 3490
        first.job_id = job.id
        db.flush()

    # 第2卷：仍在收日表。一个单边窗等待补齐，一个单边窗已注明理由排除。
    start = date(2026, 10, 31)
    late = []
    for index in range(2):
        for team, zone, size, probability, frame in (("A队", "中心区", 9, 0.95, 6200), ("A队", "外围区", 43, 0.73, 3800), ("B队", "中心区", 43, 0.89, 6200), ("B队", "外围区", 9, 0.64, 3800)):
            if index == 0 and (team, zone) == ("B队", "外围区"):
                continue  # 缺 B队/外围区，待补齐
            if index == 1 and (team, zone) == ("A队", "中心区"):
                continue  # 单边窗，示范写明理由排除
            late.append({"day": str(start + timedelta(days=index)), "team": team, "zone": zone,
                         "observed": size, "passed": max(0, size - 1), "frame_size": frame})
    second, created = build('南岭日表 · 第2卷', '南岭日表', 2, late, [{'day': str(start + timedelta(days=1)), 'zone': '中心区',
                                                                     'reason': '观察员请假，中心区A队当日无记录，按单边窗排除', 'by': admin.email, 'at': time.time()}])
    if created:
        first.next_volume_id = second.id
        db.flush()


def seed():
    migrate()
    with Session() as db:
        for role,name in [('admin','林知 · 业务负责人'),('analyst','陈舟 · 分析员'),('viewer','周禾 · 观察员')]:
            email=role+'@demo.local'
            if not db.scalar(select(User).where(User.email==email)):
                db.add(User(email=email,name=name,role=role,password=hash_password('Demo123!')))
        db.flush()
        m=metadata()
        d=db.scalar(select(Dataset).where(Dataset.name==m['dataset_name']))
        if not d:
            rows=seed_records()
            d=Dataset(name=m['dataset_name'],source=m['short']+'-202611.csv',records=rows,checksum=checksum(rows),created_at=time.time())
            db.add(d); db.flush()
        admin=db.scalar(select(User).where(User.role=='admin'))
        _seed_volumes(db, admin, m)
        if not db.scalar(select(Job).where(Job.name=='基线复核 · '+m['name'])):
            params={p['key']:p['default'] for p in m.get('parameters',[])}
            result=analyze_volume(d.records,[],params)
            json.dumps(result,ensure_ascii=False,allow_nan=False)
            j=Job(name='基线复核 · '+m['name'],dataset_id=d.id,params=params,status='completed',result=result,created_by=admin.id,created_at=time.time()-3600,finished_at=time.time()-3595,approved=True)
            db.add(j);db.flush()
            r=Report(name='每日业务复核简报',job_id=j.id,destination='业务复核组 · 本地收件箱',interval_seconds=86400,next_run=time.time()+86400,enabled=True)
            db.add(r);db.flush();deliver(db,r)
            db.add(Audit(actor='seed',action='demo.baseline',detail={'dataset':d.id},at=time.time()))
        db.commit()
        counts={model.__tablename__:db.scalar(select(func.count()).select_from(model)) for model in [User,Dataset,Volume,Job,Report,Delivery,Audit]}
        print(json.dumps(counts,ensure_ascii=False))
        return counts
if __name__=='__main__':seed()
