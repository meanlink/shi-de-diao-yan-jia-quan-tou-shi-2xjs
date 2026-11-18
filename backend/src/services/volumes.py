"""Day-table volumes: batch collection, same-day pairing, exclusions and sealing."""
import time

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.models import Dataset, Volume
from src.services import jobs as job_service
from src.services.business import normalize_records, window_report


def _get_locked(db, volume_id):
    volume = db.scalar(select(Volume).where(Volume.id == volume_id).with_for_update())
    if not volume:
        raise HTTPException(404, '日表卷不存在')
    return volume


def _summary(volume, job=None):
    try:
        report = window_report(volume.records, volume.exclusions)
        counts = {'paired_windows': len(report['paired']), 'pending_windows': len(report['pending']),
                  'excluded_windows': len(report['excluded']), 'pending': report['pending'],
                  'excluded': report['excluded'], 'windows_error': ''}
    except ValueError as error:
        # A stored volume must stay visible even if its rows became inconsistent.
        counts = {'paired_windows': 0, 'pending_windows': 0, 'excluded_windows': 0,
                  'pending': [], 'excluded': [], 'windows_error': str(error)}
    if volume.status != 'sealed':
        stage = 'collecting'
    elif job is None:
        stage = 'sealed'
    elif job.status in ('queued', 'running'):
        stage = 'computing'
    elif job.status == 'completed':
        stage = 'completed'
    else:
        stage = 'failed'
    return {
        'id': volume.id, 'name': volume.name, 'series': volume.series, 'sequence': volume.sequence,
        'dataset_id': volume.dataset_id, 'source': volume.source, 'status': volume.status, 'stage': stage,
        'sealed_at': volume.sealed_at, 'sealed_by': volume.sealed_by, 'created_at': volume.created_at,
        'next_volume_id': volume.next_volume_id, 'job_id': volume.job_id,
        'rows': len(volume.records), **counts, 'job': _job_summary(job),
    }


def _job_summary(job):
    if not job:
        return None
    return {'id': job.id, 'name': job.name, 'status': job.status, 'approved': job.approved,
            'error': job.error, 'finished_at': job.finished_at, 'params': job.params}


def detail(db, volume_id):
    volume = db.get(Volume, volume_id)
    if not volume:
        raise HTTPException(404, '日表卷不存在')
    job = db.get(job_service.Job, volume.job_id) if volume.job_id else None
    data = _summary(volume, job)
    if data['windows_error']:
        data['windows'] = {'paired': [], 'pending': [], 'excluded': []}
    else:
        data['windows'] = window_report(volume.records, volume.exclusions)
    return data


def listing(db):
    volumes = list(db.scalars(select(Volume).order_by(Volume.id.desc()).limit(50)))
    job_ids = {v.job_id for v in volumes if v.job_id}
    found = {j.id: j for j in db.scalars(select(job_service.Job).where(job_service.Job.id.in_(job_ids)))} if job_ids else {}
    return [_summary(v, found.get(v.job_id)) for v in volumes]


def create(db, data, user):
    records = normalize_records(data.records)
    name = data.name.strip()
    if db.scalar(select(Volume).where(Volume.name == name)):
        raise HTTPException(409, '该日表卷名称已存在，请修改名称')
    if data.dataset_id is not None and not db.get(Dataset, data.dataset_id):
        raise HTTPException(404, '数据批次不存在')
    sequence = data.sequence
    if sequence is None:
        sequence = 1 + (db.scalar(select(Volume.sequence).where(Volume.series == data.series).order_by(Volume.sequence.desc())) or 0)
    volume = Volume(name=name, series=data.series, sequence=sequence, dataset_id=data.dataset_id,
                    source=data.source, records=records, exclusions=[], status='collecting',
                    created_by=user.id, created_at=time.time())
    try:
        with db.begin_nested():
            db.add(volume)
            db.flush()
    except IntegrityError:
        raise HTTPException(409, '该序列的卷号已被占用，请稍后重试或指定卷号') from None
    return volume


def _next_volume(db, volume, user):
    """Return the volume that late rows should be filed into; create it when absent."""
    current = volume
    seen = set()
    while True:
        if current.id in seen:
            break
        seen.add(current.id)
        if current.status == 'collecting':
            return current
        if current.next_volume_id:
            following = db.get(Volume, current.next_volume_id)
            if following:
                current = following
                continue
        # Reuse any open volume already collecting in this series so late rows from
        # different sealed volumes cannot split into parallel chains.
        open_volume = db.scalar(select(Volume).where(Volume.series == volume.series, Volume.status == 'collecting').order_by(Volume.sequence))
        if open_volume:
            current.next_volume_id = open_volume.id
            db.flush()
            return open_volume
        sequence = 1 + (db.scalar(select(Volume.sequence).where(Volume.series == volume.series).order_by(Volume.sequence.desc())) or 0)
        following = Volume(name=f"{volume.series} 第{sequence}卷 · 迟报补收", series=volume.series, sequence=sequence,
                           dataset_id=volume.dataset_id, source=volume.source, records=[], exclusions=[],
                           status='collecting', created_by=user.id, created_at=time.time())
        try:
            with db.begin_nested():
                db.add(following)
                db.flush()
        except IntegrityError:
            # A concurrent request already created this sequence; reuse the open one.
            existing = db.scalar(select(Volume).where(Volume.series == volume.series, Volume.sequence == sequence))
            if not existing:
                raise
            following = existing
            if following.status != 'collecting':
                current = following
                continue
        current.next_volume_id = following.id
        db.flush()
        return following


def append_records(db, volume_id, rows, user):
    """File supplemental rows. A sealed volume is immutable; late rows go to the next volume."""
    volume = _get_locked(db, volume_id)
    incoming = normalize_records(rows)
    target = volume if volume.status == 'collecting' else _next_volume(db, volume, user)
    combined = list(target.records) + incoming
    normalize_records(combined)
    dropped = []
    if target.status == 'collecting' and target.exclusions:
        paired = {(w['day'], w['zone']) for w in window_report(combined, [] )['paired']}
        kept = []
        for item in target.exclusions:
            if (item['day'], item['zone']) in paired:
                dropped.append(item)
            else:
                kept.append(item)
        target.exclusions = kept
    target.records = combined
    db.flush()
    return {'accepted_volume_id': target.id, 'accepted_volume_name': target.name,
            'rerouted': target.id != volume.id, 'original_volume_id': volume.id,
            'added_rows': len(incoming), 'dropped_exclusions': dropped,
            'status': target.status}


def exclude(db, volume_id, day, zone, reason, user):
    volume = _get_locked(db, volume_id)
    if volume.status != 'collecting':
        raise HTTPException(409, '日表卷已封卷，不能再修改排除理由；请对下一卷操作')
    reason = str(reason or '').strip()
    if len(reason) < 2:
        raise HTTPException(422, '排除观察窗必须注明至少两个字符的理由')
    report = window_report(volume.records, volume.exclusions)
    if any(item['day'] == day and item['zone'] == zone for item in volume.exclusions):
        raise HTTPException(409, '该观察窗已注明排除理由；如需补报，请直接补报记录以自动撤销排除')
    matching = [w for w in report['paired'] if w['day'] == day and w['zone'] == zone]
    if matching:
        raise HTTPException(422, '该观察窗已经同日同区域配齐，应参与计算，不能排除')
    candidates = [w for w in report['pending'] if w['day'] == day and w['zone'] == zone]
    if not candidates:
        raise HTTPException(404, '未找到该单边观察窗，请核对日期与区域')
    volume.exclusions = list(volume.exclusions) + [{'day': day, 'zone': zone, 'reason': reason, 'by': user.email, 'at': time.time()}]
    db.flush()
    return detail(db, volume.id)


def unexclude(db, volume_id, day, zone):
    volume = _get_locked(db, volume_id)
    if volume.status != 'collecting':
        raise HTTPException(409, '日表卷已封卷，排除记录不可撤销')
    before = len(volume.exclusions)
    volume.exclusions = [e for e in volume.exclusions if not (e['day'] == day and e['zone'] == zone)]
    if len(volume.exclusions) == before:
        raise HTTPException(404, '未找到该排除记录')
    db.flush()
    return detail(db, volume.id)


def seal(db, volume_id, params, user):
    """Seal and (idempotently) start computation over the paired windows."""
    volume = _get_locked(db, volume_id)
    if volume.status != 'sealed':
        report = window_report(volume.records, volume.exclusions)
        if report['pending']:
            preview = '；'.join(f"{w['day']} {w['zone']} 缺{w['missing_team']}" for w in report['pending'][:3])
            raise HTTPException(409, f"尚有{len(report['pending'])}个观察窗未配齐也未排除，不能封卷：{preview}")
        if not report['paired']:
            raise HTTPException(409, '没有同日同区域配齐的观察窗，不能封卷')
        volume.status = 'sealed'
        volume.sealed_at = time.time()
        volume.sealed_by = user.email
        db.flush()
    job = job_service.create_for_volume(db, volume, params, user)
    volume.job_id = job.id
    db.flush()
    return volume, job


def compute(db, volume_id, params, user):
    volume = _get_locked(db, volume_id)
    if volume.status != 'sealed':
        raise HTTPException(409, '日表卷尚未封卷，不能计算')
    job = job_service.create_for_volume(db, volume, params, user)
    volume.job_id = job.id
    db.flush()
    return volume, job
