from fastapi import APIRouter, Depends, Query
from src.config.database import get_db
from src.middlewares.auth import current_user, can_write
from src.schemas.volume import VolumeInput, VolumeAppend, ExclusionInput, SealInput
from src.services import volumes, jobs
from src.services.audit import record
router=APIRouter(prefix='/volumes')

@router.get('')
def listing(db=Depends(get_db),u=Depends(current_user)):
    return volumes.listing(db)

@router.post('',status_code=201)
def create(data:VolumeInput,db=Depends(get_db),u=Depends(can_write)):
    v=volumes.create(db,data,u);record(db,u.email,'volume.create',{'id':v.id,'rows':len(v.records)})
    db.commit();return volumes.detail(db,v.id)

@router.get('/{id}')
def detail(id:int,db=Depends(get_db),u=Depends(current_user)):
    return volumes.detail(db,id)

@router.post('/{id}/records')
def append(id:int,data:VolumeAppend,db=Depends(get_db),u=Depends(can_write)):
    result=volumes.append_records(db,id,data.records,u)
    record(db,u.email,'volume.append',{'id':id,**{k:result[k] for k in ('accepted_volume_id','rerouted','added_rows')}})
    db.commit();return {**result,'volume':volumes.detail(db,result['accepted_volume_id'])}

@router.post('/{id}/exclusions')
def exclude(id:int,data:ExclusionInput,db=Depends(get_db),u=Depends(can_write)):
    result=volumes.exclude(db,id,data.day,data.zone,data.reason,u)
    record(db,u.email,'volume.exclude',{'id':id,'day':data.day,'zone':data.zone})
    db.commit();return result

@router.delete('/{id}/exclusions')
def unexclude(id:int,day:str=Query(min_length=8,max_length=20),zone:str=Query(min_length=1,max_length=60),db=Depends(get_db),u=Depends(can_write)):
    result=volumes.unexclude(db,id,day,zone)
    record(db,u.email,'volume.unexclude',{'id':id,'day':day,'zone':zone})
    db.commit();return result

@router.post('/{id}/seal')
def seal(id:int,data:SealInput,db=Depends(get_db),u=Depends(can_write)):
    volume,job=volumes.seal(db,id,data.params,u)
    record(db,u.email,'volume.seal',{'id':id,'job':job.id,'reused':job.status!='queued'})
    db.commit();jobs.enqueue(job.id);return volumes.detail(db,volume.id)

@router.post('/{id}/compute')
def compute(id:int,data:SealInput,db=Depends(get_db),u=Depends(can_write)):
    volume,job=volumes.compute(db,id,data.params,u)
    record(db,u.email,'volume.compute',{'id':id,'job':job.id})
    db.commit();jobs.enqueue(job.id);return volumes.detail(db,volume.id)
