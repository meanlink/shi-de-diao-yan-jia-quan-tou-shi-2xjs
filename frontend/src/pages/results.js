import {jobs} from '../api/entities.js';
import {workspace} from '../stores/workspace.js';
import {session} from '../stores/session.js';
import {heading} from '../components/common/shell.js';
import {chart} from '../components/common/chart.js';
import {table} from '../components/common/table.js';
import {status} from '../components/common/status.js';
import {esc,fmt,date,notify} from '../utils/dom.js';

function pairingSection(r){
 const p=r.pairing;
 if(!p)return '';
 const coverage=p.coverage||[], excluded=p.excluded||[], paired=p.paired||[];
 const coverageHtml='<div class="section-title"><h2>各区域配对覆盖</h2><span>同一区域内A/B两队使用同一组日期</span></div>'+(coverage.length?'<div class="table-wrap"><table><thead><tr><th>区域层</th><th>配对日数</th><th>两队日期一致</th><th>抽样框</th><th>日期范围</th></tr></thead><tbody>'+coverage.map(c=>'<tr><td>'+esc(c.zone)+'</td><td>'+c.paired_days+'</td><td>'+(c.both_teams_same_dates?'是':'否')+'</td><td>'+fmt(c.frame_size)+'</td><td>'+esc(c.days.length?c.days[0]+' 至 '+c.days[c.days.length-1]:'—')+'</td></tr>').join('')+'</tbody></table></div>':'<p class="empty small-empty">该结果未记录配对覆盖明细。</p>');
 const excludedHtml=excluded.length?'<div class="section-title"><h2>被排除的观察窗</h2><span>'+excluded.length+' 个单边窗，理由随卷留痕</span></div><div class="table-wrap"><table><thead><tr><th>观察日</th><th>区域层</th><th>仅有队伍</th><th>排除理由</th></tr></thead><tbody>'+excluded.map(w=>'<tr><td>'+esc(w.day)+'</td><td>'+esc(w.zone)+'</td><td>'+esc(w.present_team)+'（缺 '+esc(w.missing_team)+'）</td><td>'+esc(w.reason)+'</td></tr>').join('')+'</tbody></table></div>':'<div class="section-title"><h2>被排除的观察窗</h2><span>本卷没有因单边记录被排除的窗</span></div>';
 const pairedDetail=paired.length?'<details class="paired-details"><summary>逐窗核对参与的 '+paired.length+' 个配对窗</summary><div class="table-wrap short"><table><thead><tr><th>观察日</th><th>区域层</th><th>A队观察</th><th>B队观察</th></tr></thead><tbody>'+paired.map(w=>'<tr><td>'+esc(w.day)+'</td><td>'+esc(w.zone)+'</td><td>'+w.observed['A队']+'</td><td>'+w.observed['B队']+'</td></tr>').join('')+'</tbody></table></div></details>':'';
 return '<section class="panel"><div class="section-title"><h2>配对窗核对</h2><span>参与 '+(p.paired_windows??0)+' 个配对窗 · 涉及 '+(p.days??0)+' 个观察日 · 排除 '+(p.excluded_windows??0)+' 个单边窗</span></div>'+coverageHtml+excludedHtml+pairedDetail+'</section>';
}

export async function results(id){
 workspace.jobs=await jobs.list();const j=id?await jobs.get(id):(workspace.jobs.find(j=>j.id===workspace.selectedJob)||workspace.jobs[0]);
 if(j&&!workspace.jobs.some(x=>x.id===j.id))workspace.jobs.push(j);
 if(!j)return heading('04 / REVIEW','结果复核','尚无分析结果。')+'<div class="empty">先到收卷工作台，完成同区域配对后封卷计算。<a href="#/workbench">前往工作台 ↗</a></div>';
 workspace.selectedJob=j.id;const r=j.result||{};
 return heading('04 / REVIEW','结果复核与业务解释',j.name,'<button class="button" id="refresh-results">刷新结果 ↻</button>')+'<div class="result-selector"><label>分析记录<select id="select-job">'+workspace.jobs.map(x=>'<option value="'+x.id+'" '+(x.id===j.id?'selected':'')+'>'+esc(x.name)+' · '+esc(x.status)+'</option>').join('')+'</select></label>'+status(j.status)+'<span>'+date(j.created_at)+'</span><span class="approval">'+(j.approved?'已获业务批准':'待负责人复核')+'</span></div>'+(j.status==='completed'?'<section class="result-lead"><p class="eyebrow">COMPUTED FINDING</p><h2>'+esc(r.summary)+'</h2><div class="metrics">'+(r.metrics||[]).map(m=>'<div><span>'+esc(m.label)+'</span><strong>'+esc(fmt(m.value))+'<small>'+esc(m.unit||'')+'</small></strong></div>').join('')+'</div></section><section class="panel">'+chart(r.chart)+'</section>'+pairingSection(r)+'<div class="two-columns"><section class="panel"><div class="section-title"><h2>业务解释</h2><span>由计算结果生成</span></div><ol class="questions">'+(r.findings||[]).map(v=>'<li>'+esc(v)+'</li>').join('')+'</ol>'+(r.warnings||[]).map(v=>'<p class="warning">'+esc(v)+'</p>').join('')+'</section><section class="method-sheet compact"><p class="eyebrow">REPRODUCIBILITY</p><h3>计算口径与参数</h3><p>'+esc(r.method)+'</p><pre>'+esc(JSON.stringify(j.params,null,2))+'</pre>'+(session.user.role==='admin'&&!j.approved?'<button class="primary" id="approve-job">批准此业务结论</button>':'')+'<p class="hint">仅批准结果可进入定时分发档案。重试同一输入与参数会复用原结论，不重复生成。</p></section></div><section class="panel"><div class="section-title"><h2>结果明细</h2><span>'+(r.table?.rows?.length||0)+' 行</span></div>'+table(r.table?.columns||[],r.table?.rows||[])+'</section>':'<section class="panel empty">'+(j.status==='failed'?'计算失败：'+esc(j.error)+'。请返回工作台核对配对窗或参数后重试。':'后台正在执行计算。点击刷新结果查看最新进展。')+'<a href="#/workbench">返回工作台 ↗</a></section>');
}
export function bindResults(refresh){document.querySelector('#refresh-results')?.addEventListener('click',refresh);document.querySelector('#select-job')?.addEventListener('change',e=>{workspace.selectedJob=Number(e.target.value);location.hash='#/results/'+e.target.value;});document.querySelector('#approve-job')?.addEventListener('click',async()=>{try{await jobs.approve(workspace.selectedJob);notify('已批准，可创建分发计划');await refresh();}catch(e){notify(e.message,true);}});}
