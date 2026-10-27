'use strict';
const $=id=>document.getElementById(id);
let reports={},receipt=null,provenance=null,selectedQuery='correct';
function el(tag,text,className){const node=document.createElement(tag);if(text!=null)node.textContent=String(text);if(className)node.className=className;return node;}
function current(){return reports[$('sample').value];}
function utc(value){return value?value.replace('T',' ').replace('Z',' UTC'):'Not recorded';}
function rowsFor(report){const filter=$('show').value;return report.rows.filter(row=>filter==='all'||filter==='delayed'&&['completed_late','open_overdue'].includes(row.status)||filter==='review'&&row.status.startsWith('review_')||filter===row.status);}
function drawRows(){
  const report=current(),rows=rowsFor(report),body=$('orders-body');body.replaceChildren();
  rows.forEach(row=>{
    const tr=el('tr'),first=el('td'),button=el('button',row.order_id,'order-link');
    button.type='button';button.addEventListener('click',()=>inspect(row));first.append(button,el('small',row.product));
    tr.append(first,el('td',row.work_center),el('td',utc(row.due_at)),el('td',row.quantity));
    const state=el('td');state.append(el('span',row.status_label,'badge '+row.status));tr.append(state);body.append(tr);
  });
  if(!rows.length){const tr=el('tr'),td=el('td','No orders match this filter.');td.colSpan=5;tr.append(td);body.append(tr);}
  $('row-count').textContent=rows.length+' of '+report.metrics.orders+' orders shown · original synthetic data';
  $('status').textContent=$('sample').selectedOptions[0].textContent+' · '+rows.length+' orders shown for this filter.';
}
function drawSql(){
  $('sql').textContent=current().sql[selectedQuery];
  for(const key of ['correct','naive']){$('tab-'+key).setAttribute('aria-selected',String(key===selectedQuery));$('tab-'+key).tabIndex=key===selectedQuery?0:-1;}
  $('query').setAttribute('aria-labelledby','tab-'+selectedQuery);
}
function draw(){
  const report=current(),m=report.metrics,v=report.validation,q=report.quality;
  $('total').textContent=m.orders;$('units').textContent=m.units+' units in this cohort';
  $('delayed').textContent=m.delayed;$('delay-breakdown').textContent=m.completed_late+' completed late · '+m.open_overdue+' open';
  $('review').textContent=m.review;$('on-time').textContent=m.on_time;
  $('scope').textContent='Due '+utc(report.parameters.start_utc)+' up to '+utc(report.parameters.end_utc)+' (excluded). Completion evidence stops at that same cutoff.';
  $('reference-badge').textContent=v.correct_matches_reference?'REFERENCE MATCH RECORDED':'RECORDED DISAGREEMENT';
  $('reference-detail').textContent=v.expected_orders+' orders and their timing classifications were checked against the independent Python reference.';
  $('naive-count').textContent=v.naive_orders;$('reference-count').textContent=v.expected_orders;
  $('join-detail').textContent='The deliberately wrong query reports '+v.naive_units+' units instead of '+v.expected_units+', adding '+v.extra_joined_rows+' joined rows.';
  $('quality').replaceChildren(...[q.replay_rows_in_cohort+' exact replay row collapsed',q.conflicting_orders_in_cohort+' order with conflicting event copies',q.missing_completion_time_in_cohort+' order with an undated completion',q.missing_due_count+' undated order excluded from due-date cohorts'].map(text=>el('li',text)));
  $('start').textContent=report.parameters.start_utc;$('end').textContent=report.parameters.end_utc;$('fingerprint').textContent=report.dataset_sha256;
  $('download').href='data/'+$('sample').value+'.json';
  drawRows();drawSql();
}
function inspect(row){
  $('order-title').textContent=row.order_id;
  $('order-description').textContent=row.product+' · '+row.work_center+' · '+row.quantity+' units · Due '+utc(row.due_at);
  $('order-state').textContent='Recorded classification: '+row.status_label+'. '+(row.completed_at?'Selected completion: '+utc(row.completed_at)+'. ':'')+(row.replay_rows?row.replay_rows+' exact replay row was collapsed by the original report.':'');
  $('order-steps').replaceChildren(...row.steps.map(step=>el('li',step.step_name)));
  if(!row.steps.length)$('order-steps').append(el('li','No planned steps in this export.'));
  $('order-events').replaceChildren();
  row.events.forEach(event=>{const tr=el('tr');[event.record_no,event.source_event_id,utc(event.occurred_at)].forEach(value=>tr.append(el('td',value)));$('order-events').append(tr);});
  if(!row.events.length){const tr=el('tr'),td=el('td','No completion records in this export.');td.colSpan=3;tr.append(td);$('order-events').append(tr);}
  $('order-dialog').showModal();
}
function compare(){
  const before=reports.baseline,after=reports['after-import'];
  const compatible=JSON.stringify(before.parameters)===JSON.stringify(after.parameters)&&before.definition===after.definition&&before.sql.correct===after.sql.correct;
  $('comparison-policy').textContent=compatible?'Both exports use the same UTC date range, report definition and SQL. The saved baseline remains unchanged.':'The report definitions differ. Counts are displayed, but their difference should not be interpreted as a like-for-like change.';
  const ids=new Set(before.rows.map(row=>row.order_id)),added=after.rows.filter(row=>!ids.has(row.order_id));
  $('delta').textContent=compatible?added.length+' added orders · '+(after.metrics.units-before.metrics.units)+' additional units · '+(after.metrics.delayed-before.metrics.delayed)+' additional delayed orders':'Compare the definitions before interpreting a count difference.';
  $('added-orders').replaceChildren(...added.map(row=>el('li',row.order_id+' · '+row.product+' · '+row.status_label)));
  const body=$('comparison-rows');body.replaceChildren();
  [['Saved baseline',before],['After sample import',after],['Earlier snapshot after reload',before]].forEach(([label,report])=>{const tr=el('tr'),th=el('th',label);th.scope='row';tr.append(th);[report.metrics.orders,report.metrics.units,report.metrics.delayed].forEach(value=>tr.append(el('td',value)));body.append(tr);});
}
function checkReport(value){
  if(value.synthetic!==true||!Array.isArray(value.rows)||value.rows.length!==value.metrics.orders||!value.validation.correct_matches_reference)throw new Error('The sample export failed its recorded-data checks.');
  return value;
}
$('sample').addEventListener('change',draw);$('show').addEventListener('change',drawRows);$('close').addEventListener('click',()=>$('order-dialog').close());
for(const button of document.querySelectorAll('[data-query]')){
  button.addEventListener('click',()=>{selectedQuery=button.dataset.query;drawSql();});
  button.addEventListener('keydown',event=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();selectedQuery=event.key==='Home'?'correct':event.key==='End'?'naive':selectedQuery==='correct'?'naive':'correct';drawSql();$('tab-'+selectedQuery).focus();});
}
(async()=>{
  try{
    const names=['baseline','after-import','receipt','provenance'];
    const loaded=await Promise.all(names.map(async name=>{const response=await fetch('data/'+name+'.json',{cache:'no-cache'});if(!response.ok)throw new Error('Sample exports could not be loaded.');return response.json();}));
    reports={baseline:checkReport(loaded[0]),'after-import':checkReport(loaded[1])};receipt=loaded[2];provenance=loaded[3];
    if(receipt.dataset_sha256_before!==reports.baseline.dataset_sha256||receipt.dataset_sha256_after!==reports['after-import'].dataset_sha256)throw new Error('The receipt does not match these sample reports.');
    $('provenance-note').textContent='Captured through Workfloor '+reports.baseline.version+' on '+provenance.captured_at+'. The downloaded receipt matches the original CSV SHA-256; all sample file hashes are listed in the provenance record.';
    $('sample').disabled=false;$('show').disabled=false;compare();draw();
  }catch(error){$('error').hidden=false;$('error').textContent='The sample reports could not be loaded consistently. Reload this page or open the linked repository to inspect the exports. '+error.message;$('status').textContent='Sample reports unavailable.';$('download').removeAttribute('href');}
})();
