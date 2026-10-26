'use strict';
let csvText = '', csvPreview = null, importReceipt = null;
const csvColumns = ['order_id','product','work_center','quantity','due_at','completed_at'];
function importMessage(text, error=false) {
  $('csv-message').textContent=text;
  $('csv-message').classList.toggle('error',error);
}
function updateImportControls() {
  ['csv-file','csv-synthetic','csv-valid','csv-errors','csv-clear'].forEach(id=>$(id).disabled=busy);
  $('csv-preview').disabled=busy||!meta||!csvText||!$('csv-synthetic').checked;
  $('csv-apply').disabled=busy||!csvPreview?.can_import||!$('csv-synthetic').checked;
  $('csv-download').disabled=busy||!importReceipt;
}
function invalidatePreview() {
  csvPreview=null;
  $('csv-rows').replaceChildren();
  $('csv-results').hidden=true;
  updateImportControls();
}
function selectCsv(text,name) {
  csvText=text;
  $('csv-file-name').textContent=name;
  invalidatePreview();
  importMessage('File ready. Confirm it uses invented data, then preview every row. Nothing has been imported.');
}
function drawCsvPreview() {
  const data=csvPreview;
  $('csv-results').hidden=false;
  $('csv-summary').textContent=data.total_rows+' records · '+data.valid_rows+' valid · '+data.invalid_rows+' with issues';
  $('csv-summary').className='import-summary '+(data.can_import?'ready':'blocked');
  $('csv-fingerprint').textContent='Previewed file SHA-256: '+data.csv_sha256.slice(0,16)+'…';
  const issues=$('csv-issues');
  issues.replaceChildren();issues.hidden=!data.invalid_rows;
  data.rows.filter(row=>row.errors.length).forEach(row=>{
    const item=element('div',null,'import-issue');
    item.append(element('strong',(row.values.order_id||'Order ID missing')+' · CSV line '+row.line));
    const list=element('ul');
    row.errors.forEach(error=>list.append(element('li',error)));
    item.append(list);issues.append(item);
  });
  const body=$('csv-rows');
  body.replaceChildren();
  data.rows.forEach(row=>{
    const tr=element('tr');
    csvColumns.forEach((name,index)=>{
      const td=element('td');
      td.append(element(index===0?'strong':'span',row.values[name]||(name==='completed_at'?'No completion recorded':'—')));
      if(index===0) td.append(element('small','CSV line '+row.line));
      tr.append(td);
    });
    const state=element('td',null,'import-row-status');
    if(row.errors.length){
      state.append(element('span','FIX BEFORE IMPORT','badge fail'));
      state.append(element('small',row.errors.length+(row.errors.length===1?' issue':' issues')+' listed above'));
    }else state.append(element('span','READY','badge pass'));
    tr.append(state);body.append(tr);
  });
  importMessage(data.can_import
    ?'All '+data.total_rows+' records passed. Review the preview, then import them together. Your database is unchanged until you apply.'
    :'Import blocked. Fix every listed issue and preview again. No rows were imported.',!data.can_import);
}
async function previewCsv() {
  if(busy||!csvText||!$('csv-synthetic').checked)return;
  invalidatePreview();setBusy(true);importMessage('Checking every row against the current source. Preview does not write data…');
  try{
    csvPreview=await api('/api/imports/preview',{method:'POST',headers:{'Content-Type':'application/json','X-Workbench-Token':meta.token},body:JSON.stringify({csv_text:csvText,synthetic:true})});
    drawCsvPreview();
  }catch(error){importMessage(error.message,true);}
  finally{setBusy(false);}
}
function downloadImportReceipt() {
  if(!importReceipt)return;
  const url=URL.createObjectURL(new Blob([JSON.stringify(importReceipt,null,2)],{type:'application/json'}));
  const link=element('a');link.href=url;link.download='workfloor-import-'+importReceipt.import_id.slice(0,8)+'.json';
  document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
async function applyCsv() {
  if(busy||!csvPreview?.can_import||!$('csv-synthetic').checked)return;
  setBusy(true);importMessage('Rechecking this file and source, then importing all rows in one transaction…');
  try{
    importReceipt=await api('/api/imports/apply',{method:'POST',headers:{'Content-Type':'application/json','X-Workbench-Token':meta.token},body:JSON.stringify({csv_text:csvText,synthetic:true,dataset_sha256:csvPreview.dataset_sha256,preview_token:csvPreview.preview_token})});
    invalidatePreview();
    $('csv-receipt').textContent='Last successful import: '+importReceipt.orders_added+' orders · '+importReceipt.imported_at+' · '+importReceipt.import_id.slice(0,8)+'. Existing records and snapshots were retained.';
    importMessage('Imported '+importReceipt.orders_added+' new orders and '+importReceipt.completion_events_added+' completion events. Download the receipt to keep its file and dataset fingerprints.');
    report=null;savedView=false;
    $('view-state').textContent='RELOAD REQUIRED';
    ['total','units','delayed','delay-breakdown','review','on-time','dataset-count'].forEach(id=>$(id).textContent='—');
    try{
      report=await api('/api/report?'+new URLSearchParams({start:$('start').value,end:$('end').value}));
      drawReport();await loadHistory();
      message('Current report refreshed after import. Earlier saved snapshots still preserve their original results.');
    }catch(error){message('Import committed, but the report could not refresh. Run the report again. '+error.message,true);}
  }catch(error){
    invalidatePreview();
    importMessage(error.message+' Preview again before retrying; existing order IDs cannot be overwritten.',true);
  }finally{setBusy(false);}
}
async function loadCsvSample(path,name) {
  if(busy)return;
  setBusy(true);
  try{
    const response=await fetch(path,{cache:'no-store'});
    if(!response.ok)throw new Error('The sample CSV could not be loaded.');
    selectCsv(await response.text(),name);
    $('csv-file').value='';$('csv-synthetic').checked=true;
    importMessage('Original invented sample loaded. Preview it to see row validation before applying.');
  }catch(error){importMessage(error.message,true);}
  finally{setBusy(false);}
}
$('csv-file').addEventListener('change',async()=>{
  if(busy)return;
  csvText='';invalidatePreview();$('csv-synthetic').checked=false;
  const file=$('csv-file').files[0];
  if(!file){$('csv-file-name').textContent='No file selected';updateImportControls();return;}
  $('csv-file-name').textContent=file.name;
  if(file.size===0||file.size>256*1024){importMessage('Choose a nonempty CSV file of at most 256 KiB.',true);updateImportControls();return;}
  setBusy(true);
  // Include a UTF-8 BOM in the text so the server hashes the original file bytes.
  try{selectCsv(new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(await file.arrayBuffer()),file.name);}
  catch{importMessage('This file is not valid UTF-8. Save it as UTF-8 CSV and choose it again.',true);}
  finally{setBusy(false);}
});
$('csv-synthetic').addEventListener('change',()=>{invalidatePreview();importMessage('Confirm the file uses invented data, then preview again.');});
$('csv-valid').addEventListener('click',()=>loadCsvSample('/examples/import-valid.csv','import-valid.csv · 3 invented work orders'));
$('csv-errors').addEventListener('click',()=>loadCsvSample('/examples/import-errors.csv','import-errors.csv · intentional validation failures'));
$('csv-preview').addEventListener('click',previewCsv);
$('csv-apply').addEventListener('click',applyCsv);
$('csv-download').addEventListener('click',downloadImportReceipt);
$('csv-clear').addEventListener('click',()=>{$('csv-file').value='';csvText='';$('csv-file-name').textContent='No file selected';$('csv-synthetic').checked=false;invalidatePreview();importMessage('Choose a CSV or load a sample. Preview does not change your database.');});
updateImportControls();
