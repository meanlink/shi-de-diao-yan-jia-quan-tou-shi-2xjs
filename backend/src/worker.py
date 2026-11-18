import time, json, logging
from pathlib import Path
from sqlalchemy import select, update
from redis import Redis
from src.config.database import Session
from src.config.settings import REDIS_URL
from src.models import Job, Dataset, Report, Volume
from src.services.business import analyze_volume
from src.services.reports import deliver
from src.services.audit import record
logging.basicConfig(level=logging.INFO)


def _source(db, job):
    """Volume-bound jobs always read the frozen volume, never a mutable dataset."""
    if job.volume_id:
        volume = db.get(Volume, job.volume_id)
        if not volume:
            raise ValueError('该分析绑定的日表卷已不存在')
        return volume.records, volume.exclusions
    dataset = db.get(Dataset, job.dataset_id)
    if not dataset:
        raise ValueError('该分析绑定的数据批次已不存在')
    return dataset.records, []


def _claim(db, job_id):
    """Atomically move queued -> running. A duplicate delivery loses the claim."""
    claimed = db.execute(
        update(Job).where(Job.id == job_id, Job.status == 'queued').values(status='running')
    ).rowcount
    db.commit()
    return claimed == 1


def execute(job_id):
    with Session() as db:
        if not _claim(db, job_id):
            return
        j=db.get(Job,job_id)
        try:
            records,exclusions=_source(db,j)
            result=analyze_volume(records,exclusions,j.params)
            json.dumps(result,allow_nan=False)
            j.result=result;j.status='completed';j.error='';j.finished_at=time.time()
            record(db,'worker','job.completed',{'id':j.id,'volume':j.volume_id})
        except Exception as e:
            logging.exception('Analysis failed')
            j.status='failed';j.error=str(e)[:990];j.finished_at=time.time()
            record(db,'worker','job.failed',{'id':j.id,'volume':j.volume_id,'error':j.error})
        db.commit()


def tick():
    with Session() as db:
        queued=list(db.scalars(select(Job.id).where(Job.status=='queued').order_by(Job.id).limit(3)))
    for job_id in queued:execute(job_id)
    with Session() as db:
        for r in db.scalars(select(Report).where(Report.enabled==True,Report.next_run<=time.time())):
            d=deliver(db,r)
            if d:record(db,'worker','report.delivered',{'id':r.id,'delivery':d.id})
        db.commit()


def main():
    r=Redis.from_url(REDIS_URL,socket_timeout=3)
    # This Compose stack has a single worker. A crash must not strand its jobs.
    # Completed jobs are never re-run, so a restart cannot duplicate conclusions.
    with Session() as db:
        for j in db.scalars(select(Job).where(Job.status=='running')):
            j.status='queued';record(db,'worker','job.recovered',{'id':j.id,'volume':j.volume_id})
        db.commit()
    while True:
        Path('/tmp/heartbeat').touch()
        try:
            item=r.blpop('analysis:queue',timeout=1)
            if item:execute(int(item[1]))
            tick()
        except Exception:
            logging.exception('Worker retry');time.sleep(2)


if __name__=='__main__':main()
