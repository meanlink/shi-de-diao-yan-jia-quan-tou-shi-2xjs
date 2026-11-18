import {volumes} from '../api/entities.js';
import {workspace} from '../stores/workspace.js';
import {session} from '../stores/session.js';
import {heading} from '../components/common/shell.js';
import {status} from '../components/common/status.js';
import {esc,notify,date} from '../utils/dom.js';
import {submit} from '../hooks/forms.js';
import {parseCSV} from '../utils/csv.js';
import {VolumeStage} from '../constants/enums.js';

const badge=v=>'<span class="stage stage-'+esc(v)+'">'+esc(VolumeStage[v]||v)+'</span>';

function windowTable(title,note,rows,builder){
 if(!rows.length)return '<div class="section-title"><h2>'+esc(title)+'</h2><span>'+esc(note)+'</span></div><p class="empty small-empty">暂无此类观察窗。</p>';
 return '<div class="section-title"><h2>'+esc(title)+'</h2><span>'+esc(note)+'</span></div><div class="table-wrap"><table><thead><tr><th>观察日</th><th>区域层</th><th>记录</th><th>说明 / 操作</th></tr></thead><tbody>'+rows.map(builder).join('')+'</tbody></table></div>';
}

export async function workbench(){
 const list=await volumes.list();workspace.volumes=list;
 const m=workspace.meta,canWrite=session.user.role!=='viewer';
 const id=workspace.selectedVolume;
 const current=list.find(v=>v.id===id)||list[0];
 const detail=current?await volumes.get(current.id):null;
 if(detail)workspace.selectedVolume=detail.id;
 const collecting=detail?.status==='collecting';
 const params=m.parameters;

 const listHtml='<section class="panel volume-panel"><div class="section-title"><h2>日表卷</h2><span>'+list.length+' 卷 · 待补齐到计算完成</span></div><div class="volume-list">'+(list.length?list.map(v=>'<button class="volume-item '+(v.id===current?.id?'active':'')+'" data-volume="'+v.id+'"><div><strong>'+esc(v.name)+'</strong><span>'+badge(v.stage)+'</span></div><small>'+v.rows+' 行 · 配对 '+v.paired_windows+' · 待补 '+v.pending_windows+' · 排除 '+v.excluded_windows+'</small></button>').join(''):'<p class="empty">尚无日表卷。先在右侧建立第一卷，分批收日表。</p>')+'</div>'+
   '<div class="section-title"><h2>新建日表卷</h2></div><form id="volume-form"><label>卷名称<input name="name" required minlength="2" placeholder="例如：南岭日表 · 第3卷"></label><label>序列<select name="series"><option value="南岭日表">南岭日表</option></select></label><label>上传日表 CSV 或 JSON<input type="file" id="volume-file" accept=".json,.csv"></label><label>记录 JSON<textarea name="records" rows="6" placeholder="粘贴 JSON 数组，或先选择上方文件" required></textarea></label><p class="hint">字段：'+m.columns.map(c=>esc(c.key)+' / '+esc(c.label)).join('，')+'。可分批导入，未配齐的窗会在此卷标出。</p><button type="submit" class="primary" '+(canWrite?'':'disabled')+'>建立日表卷</button></form></section>';

 let detailHtml='<section class="panel volume-detail"><div class="empty">先建立或选择一卷日表，查看配对情况。</div></section>';
 if(detail){
   const job=detail.job;
   const jobBlock=job?'<div class="volume-job">'+status(job.status)+' <a href="#/results/'+job.id+'">查看结果与配对明细 ↗</a>'+(job.status==='failed'?'<p class="warning">'+esc(job.error)+'</p>':'')+'</div>':'';
   const pending=windowTable('待补齐观察窗','单边记录，须补齐或注明理由排除，否则不能封卷',detail.windows.pending,w=>'<tr><td>'+esc(w.day)+'</td><td>'+esc(w.zone)+'</td><td>仅有 '+esc(w.present_team)+' · 缺 '+esc(w.missing_team)+'</td><td class="action-cell">'+(collecting&&canWrite?'<input class="inline-input" data-reason="'+esc(w.day)+'|'+esc(w.zone)+'" placeholder="排除理由，至少两个字"><button class="button small" data-exclude="'+esc(w.day)+'|'+esc(w.zone)+'">注明理由排除</button>':'<span class="muted">待补齐；封卷后可补报进入下一卷</span>')+'</td></tr>');
   const excluded=windowTable('已排除观察窗','单边窗因故不参与计算，理由随卷留痕',detail.windows.excluded,w=>'<tr><td>'+esc(w.day)+'</td><td>'+esc(w.zone)+'</td><td>仅有 '+esc(w.present_team)+'</td><td>'+esc(w.reason)+(collecting&&canWrite?' <button class="text-button" data-unexclude="'+esc(w.day)+'|'+esc(w.zone)+'">撤销</button>':'')+'</td></tr>');
   const paired=windowTable('参与计算的配对窗','同日同区域A/B两队均有记录，两队在各区域使用同一组日期',detail.windows.paired,w=>'<tr><td>'+esc(w.day)+'</td><td>'+esc(w.zone)+'</td><td>A队 '+w.observed['A队']+' · B队 '+w.observed['B队']+'</td><td class="muted">已配齐</td></tr>');
   const sealForm=collecting?'<form id="seal-form"><div class="section-title"><h2>封卷并计算</h2><span>封卷后原卷不改；迟报转入下一卷</span></div><div class="parameter-grid">'+params.map(p=>'<label>'+esc(p.label)+(p.type==='select'?'<select name="param-'+esc(p.key)+'">'+p.options.map(o=>'<option value="'+esc(o.value)+'" '+(o.value==p.default?'selected':'')+'>'+esc(o.label)+'</option>').join('')+'</select>':'<input type="number" step="any" name="param-'+esc(p.key)+'" value="'+esc(p.default)+'" min="'+esc(p.min??'')+'" max="'+esc(p.max??'')+'">')+'</label>').join('')+'</div><button type="submit" class="primary" '+(canWrite?'':'disabled')+'>封卷并计算配对加权率 ↗</button><p class="hint">仍有待补齐且未排除的观察窗时，封卷会被拒绝并列出缺口。</p></form>':'<div class="volume-sealed"><strong>已封卷</strong><span>'+esc(detail.sealed_by||'')+' · '+(detail.sealed_at?date(detail.sealed_at):'')+'</span>'+(canWrite?'<form id="recompute-form"><label>敏感性比较（新参数生成新结论，不改原卷）<select name="weight_mode">'+params.find(p=>p.key==='weight_mode').options.map(o=>'<option value="'+esc(o.value)+'" '+(o.value==='population'?'selected':'')+'>'+esc(o.label)+'</option>').join('')+'</select></label><input type="hidden" name="param-minimum_cell" value="'+esc(params.find(p=>p.key==='minimum_cell').default)+'"><button type="submit" class="button">用此口径重新计算 ↗</button></form>':'')+'</div>';
   const append=canWrite?'<form id="append-form"><div class="section-title"><h2>'+(collecting?'补报日表':'迟报补报')+'</h2><span>'+(collecting?'补齐先落定即入本卷；封卷先落定则转入下一卷':'本卷已封卷，迟报自动归入下一卷，原卷不改')+'</span></div><label>补报 CSV 或 JSON<input type="file" id="append-file" accept=".json,.csv"></label><label>补报记录 JSON<textarea name="records" rows="4" placeholder="例如只补缺失队伍的当日记录"></textarea></label><button type="submit" class="button">'+(collecting?'补报到此卷':'提交迟报（归下一卷）')+'</button></form>':'';
   detailHtml='<section class="panel volume-detail"><div class="section-title"><h2>'+esc(detail.name)+'</h2><span>'+badge(detail.stage)+' · '+detail.rows+' 行 · 配对 '+detail.paired_windows+' / 待补 '+detail.pending_windows+' / 排除 '+detail.excluded_windows+'</span></div>'+(detail.windows_error?'<p class="warning">本卷记录校验未通过：'+esc(detail.windows_error)+'</p>':'')+jobBlock+(detail.pending_windows?'<p class="warning">尚有 '+detail.pending_windows+' 个观察窗只有单边记录且未注明排除理由，封卷会被挡住。</p>':'')+pending+excluded+paired+sealForm+append+'</section>';
 }
 return heading('03 / VOLUME WORKBENCH','日表收卷与同日同区域配对','两队出勤日期不同，直接加权会把日况差异算成队伍差异。分批收日表，按同日同区域配对；只有配齐的窗参与加权。','<div class="heading-actions"><button class="button" id="refresh-volumes">刷新卷状态 ↻</button>'+(detail?.job_id?'<a class="button" href="#/results/'+detail.job_id+'">'+(detail.stage==='completed'?'查看本卷结果 ↗':'计算结果 ↗')+'</a>':'')+'</div>')+'<div class="volume-grid">'+listHtml+detailHtml+'</div>';
}

function parseInput(text,filename){const raw=filename&&filename.endsWith('.csv')?parseCSV(text):JSON.parse(text);return raw;}

export function bindWorkbench(refresh){
 document.querySelector('#refresh-volumes')?.addEventListener('click',refresh);
 document.querySelectorAll('[data-volume]').forEach(b=>b.onclick=()=>{workspace.selectedVolume=Number(b.dataset.volume);refresh();});
 const file=document.querySelector('#volume-file');
 if(file)file.addEventListener('change',async e=>{try{const f=e.target.files[0];if(!f)return;document.querySelector('#volume-form [name=records]').value=JSON.stringify(parseInput(await f.text(),f.name),null,2);}catch(error){notify(error.message,true);}});
 const vform=document.querySelector('#volume-form');
 if(vform)submit(vform,async f=>{const v=await volumes.create({name:f.get('name'),series:f.get('series'),source:'manual.json',records:JSON.parse(f.get('records'))});workspace.selectedVolume=v.id;notify('日表卷已建立，可查看待补齐观察窗');await refresh();});
 const aform=document.querySelector('#append-form');
 if(aform){
   const afile=document.querySelector('#append-file');
   if(afile)afile.addEventListener('change',async e=>{try{const file=e.target.files[0];if(!file)return;aform.querySelector('[name=records]').value=JSON.stringify(parseInput(await file.text(),file.name),null,2);}catch(error){notify(error.message,true);}});
   submit(aform,async f=>{if(!f.get('records'))throw new Error('请先粘贴或选择要补报的记录');const r=await volumes.append(workspace.selectedVolume,JSON.parse(f.get('records')));notify(r.rerouted?'原卷已封卷，补报已转入「'+r.volume.name+'」':'补报已落定本卷');await refresh();});
 }
 document.querySelectorAll('[data-exclude]').forEach(b=>b.onclick=async()=>{const [day,zone]=b.dataset.exclude.split('|');const input=Array.from(document.querySelectorAll('[data-reason]')).find(i=>i.dataset.reason===b.dataset.exclude);const reason=input?.value||'';try{await volumes.exclude(workspace.selectedVolume,{day,zone,reason});notify('已注明理由排除该观察窗');await refresh();}catch(e){notify(e.message,true);}});
 document.querySelectorAll('[data-unexclude]').forEach(b=>b.onclick=async()=>{const [day,zone]=b.dataset.unexclude.split('|');try{await volumes.unexclude(workspace.selectedVolume,day,zone);notify('已撤销排除');await refresh();}catch(e){notify(e.message,true);}});
 const sform=document.querySelector('#seal-form');
 if(sform)submit(sform,async f=>{const p={};for(const item of workspace.meta.parameters){const v=f.get('param-'+item.key);if(v!=null)p[item.key]=item.type==='number'?Number(v):v;}const r=await volumes.compute(workspace.selectedVolume,p,true);notify('已封卷，后台计算配对加权');workspace.selectedJob=r.job_id;if(r.job_id)location.hash='#/results/'+r.job_id;else await refresh();});
 const rform=document.querySelector('#recompute-form');
 if(rform)submit(rform,async f=>{const p={weight_mode:f.get('weight_mode'),minimum_cell:Number(f.get('param-minimum_cell'))};const r=await volumes.compute(workspace.selectedVolume,p,false);notify('已用新口径发起计算');workspace.selectedJob=r.job_id;await refresh();});
}
