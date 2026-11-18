import {api} from './client.js';
export const datasets={list:()=>api('/datasets'),get:id=>api('/datasets/'+id),create:data=>api('/datasets',{method:'POST',body:JSON.stringify(data)})};
export const jobs={list:()=>api('/jobs'),get:id=>api('/jobs/'+id),create:data=>api('/jobs',{method:'POST',body:JSON.stringify(data)}),approve:id=>api('/jobs/'+id+'/approve',{method:'POST'})};
export const volumes={
 list:()=>api('/volumes'),
 get:id=>api('/volumes/'+id),
 create:data=>api('/volumes',{method:'POST',body:JSON.stringify(data)}),
 append:(id,records)=>api('/volumes/'+id+'/records',{method:'POST',body:JSON.stringify({records})}),
 exclude:(id,data)=>api('/volumes/'+id+'/exclusions',{method:'POST',body:JSON.stringify(data)}),
 unexclude:(id,day,zone)=>api('/volumes/'+id+'/exclusions?day='+encodeURIComponent(day)+'&zone='+encodeURIComponent(zone),{method:'DELETE'}),
 compute:(id,params,seal)=>api('/volumes/'+id+(seal?'/seal':'/compute'),{method:'POST',body:JSON.stringify({params})})
};
export const reports={list:()=>api('/reports'),create:data=>api('/reports',{method:'POST',body:JSON.stringify(data)}),toggle:id=>api('/reports/'+id+'/toggle',{method:'POST'}),deliveries:()=>api('/deliveries')};
