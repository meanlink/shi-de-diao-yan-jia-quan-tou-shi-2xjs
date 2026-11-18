import hashlib, json, time
from fastapi import HTTPException
from redis import Redis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from src.config.settings import REDIS_URL
from src.models import Dataset, Job
from src.services.business import metadata


def _validated_params(raw):
    allowed = {p['key']: p for p in metadata().get('parameters', [])}
    if set(raw) - set(allowed):
        raise HTTPException(422, '包含未知分析参数')
    params = {k: p['default'] for k, p in allowed.items()}
    params.update(raw)
    for key, p in allowed.items():
        v = params[key]
        if p['type'] == 'number':
            try:
                v = float(v)
                if not (p.get('min', -1e9) <= v <= p.get('max', 1e9)):
                    raise ValueError()
                params[key] = v
            except (ValueError, TypeError):
                raise HTTPException(422, f'{p["label"]} 超出范围或非数值')
        elif str(v) not in [str(o['value']) for o in p.get('options', [])]:
            raise HTTPException(422, f'{p["label"]} 不是有效选项')
    return params


def create(db, data, user):
    if not db.get(Dataset, data.dataset_id):
        raise HTTPException(404, '数据批次不存在')
    params = _validated_params(data.params)
    j = Job(name=data.name, dataset_id=data.dataset_id, params=params, created_by=user.id, created_at=time.time(), status='queued')
    db.add(j)
    db.flush()
    return j


def _fingerprint(volume, params):
    payload = json.dumps({'volume': volume.id, 'records': volume.records, 'exclusions': volume.exclusions,
                          'params': params}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def create_for_volume(db, volume, raw_params, user):
    """Idempotent per (volume, input fingerprint, params): retries never duplicate conclusions."""
    params = _validated_params(raw_params)
    key = _fingerprint(volume, params)
    existing = db.scalar(select(Job).where(Job.idempotency_key == key))
    if existing:
        _rearm(existing, db)
        return existing
    j = Job(name=f"{volume.name} · 配对加权", dataset_id=volume.dataset_id, volume_id=volume.id,
            idempotency_key=key, params=params, created_by=user.id, created_at=time.time(), status='queued')
    try:
        with db.begin_nested():
            db.add(j)
            db.flush()
    except IntegrityError:
        # A concurrent seal/compute won the same fingerprint; reuse its job.
        existing = db.scalar(select(Job).where(Job.idempotency_key == key))
        if not existing:
            raise
        _rearm(existing, db)
        return existing
    return j


def _rearm(job, db):
    if job.status == 'failed':
        job.status = 'queued'
        job.error = ''
        job.finished_at = None
        db.flush()


def enqueue(job_id):
    try:
        r = Redis.from_url(REDIS_URL)
        r.rpush('analysis:queue', job_id)
        r.close()
    except Exception:
        pass  # SQL queued status is the durable fallback
