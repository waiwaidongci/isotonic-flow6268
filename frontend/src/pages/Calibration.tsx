import {useState} from 'react';
import {PageHeading} from '../components/common/PageHeading';
import {Table} from '../components/common/Table';
import {Status} from '../components/common/Status';
import {Notice} from '../components/common/Notice';
import {useTask} from '../hooks/useTask';
import {sourceApi} from '../api/source';
import {clock,fmt} from '../utils/format';

const newInstrumentExample={name:'压差仪 DP-2',serial:'DP-2026-002',description:'独立滤片压差测量'};
const calibrationExample={instrument_id:0,note:'重新校准：2026-11 起更换传感器并重新标零',segments:[
 {effective_from:'2026-10-01T00:00:00Z',effective_to:'2026-11-01T00:00:00Z',multiplier:1.0,offset:0.0,note:'原厂校准'},
 {effective_from:'2026-11-01T00:00:00Z',effective_to:null,multiplier:1.08,offset:0.15,note:'更换传感器后'},
]};

function SegmentList({segments}:{segments:any[]}){
 return <Table headers={['生效开始 (UTC)','生效结束','倍率','零点 kPa']}>{segments.map((s,i)=><tr key={i}><td>{s.effective_from}</td><td>{s.effective_to||'至今'}</td><td>{s.multiplier}</td><td>{s.offset}</td></tr>)}</Table>;
}

export function CalibrationPage({studies,instruments,user,reloadSource,reloadResearch}:any){
 const [instrumentId,S]=useState(0),[instrumentRaw,IR]=useState(JSON.stringify(newInstrumentExample,null,2)),[calibrationRaw,CR]=useState(JSON.stringify(calibrationExample,null,2)),[published,setPublished]=useState<any>(null),[traceStudyId,setTraceStudyId]=useState(0),[trace,setTrace]=useState<any>(null),[history,H]=useState<any[]>([]);
 const task=useTask();
 const instrument=(instruments||[]).find((i:any)=>i.id===(instrumentId||instruments?.[0]?.id));
 async function loadHistory(id:number){if(!id){H([]);return}try{H(await sourceApi.calibrations(id))}catch{H([])}}
 return <>
  <PageHeading index="07" title="校准一更正，旧读数换了含义。" description="先记录仪器与测量时刻，再按测量时刻所在有效时段的倍率与零点校正压差；原始值原样保留。校准可分段更正，重叠或缺口逐片指出。"/>
  <Notice {...task}/>
  <div className="source-layout">
   <section>
    <h2>压差仪与当前生效校准</h2>
    {!(instruments||[]).length&&<p>还没有登记仪器。未绑定仪器的旧研究继续沿用原分析（只用原始压差）。</p>}
    <Table headers={['仪器','序列号','当前校准','版本','生效时段']}>
     {(instruments||[]).map((i:any)=><tr key={i.id}><td>{i.name}</td><td>{i.serial}</td><td>{i.active_calibration?<Status value={i.active_calibration.status}/>:'无'}</td><td>{i.active_calibration?`v${i.active_calibration.version}`:'—'}</td><td>{i.active_calibration?i.active_calibration.segments.map((s:any)=>`${s.effective_from.slice(0,10)}→${s.effective_to?s.effective_to.slice(0,10):'至今'}`).join(' / '):'—'}</td></tr>)}
    </Table>
    <h2 className="spaced">研究 → 仪器绑定</h2>
    <Table headers={['研究','绑定仪器','处理方式','重算']}>
     {(studies||[]).map((s:any)=>{const bound=(instruments||[]).find((i:any)=>i.id===s.instrument_id);return <tr key={s.id}><td>{s.name}</td><td>{bound?`${bound.name} / ${bound.serial}`:'未绑定（沿用原分析）'}</td><td>{bound?<span className="brass">按测量时刻分段校正</span>:<span className="brass">沿用原分析</span>}</td><td>{user.role!=='viewer'&&<select defaultValue={s.instrument_id||''} onChange={e=>task.act(async()=>{await sourceApi.bind(s.id,{instrument_id:e.target.value?+e.target.value:null});await reloadSource();await reloadResearch()},'研究绑定已更新，受影响研究已排队重算')}><option value="">未绑定</option>{(instruments||[]).map((i:any)=><option key={i.id} value={i.id}>{i.name}</option>)}</select>}</td></tr>})}
    </Table>
    <h2 className="spaced">登记新仪器</h2>
    {user.role!=='viewer'?<div className="input-panel"><form onSubmit={e=>{e.preventDefault();task.act(async()=>{const made=await sourceApi.createInstrument(JSON.parse(instrumentRaw));await reloadSource();S(made.id)},'压差仪已登记')}}><label>仪器 JSON<textarea rows={6} value={instrumentRaw} onChange={e=>IR(e.target.value)}/></label><button className="primary" disabled={task.busy}>登记仪器 →</button></form></div>:<p>观察员只读。</p>}
   </section>
   <section className="input-panel">
    <small>CALIBRATION VERSION</small>
    <h2>发布更正校准</h2>
    <label>仪器<select value={instrument?.id||''} onChange={e=>{S(+e.target.value);setPublished(null);loadHistory(+e.target.value)}}>{(instruments||[]).map((i:any)=><option key={i.id} value={i.id}>{i.name}</option>)}</select></label>
    {instrument?.active_calibration&&<><p>当前生效 v{instrument.active_calibration.version}，发布后旧版保留为历史。</p><SegmentList segments={instrument.active_calibration.segments}/></>}
    {history.length>1&&<details><summary>历史校准版本 / {history.length}</summary>{history.map((v:any)=><div key={v.id}><p>v{v.version} / {v.status} / {v.created_by} / {clock(v.created_at)}{v.note?` / ${v.note}`:''}</p><SegmentList segments={v.segments}/></div>)}</details>}
    {user.role!=='viewer'&&instrument?<form onSubmit={e=>{e.preventDefault();task.act(async()=>{const body=JSON.parse(calibrationRaw);body.instrument_id=instrument.id;const result=await sourceApi.publishCalibration(instrument.id,body);setPublished(result);await reloadSource();await reloadResearch()},'校准已发布，受影响研究已排队重算')}}><label>校准 JSON<textarea rows={15} value={calibrationRaw} onChange={e=>CR(e.target.value)}/></label><button className="primary" disabled={task.busy}>发布校准版本 →</button></form>:<p>观察员只读。</p>}
   </section>
  </div>
  {published&&<section className="ledger-section"><div className="section-head"><h2>本次发布的受影响滤片</h2><span>版本 v{published.version} / 重算 {published.recompute?.length||0} 项研究</span></div>
   {published.diagnostics?.overlaps?.length>0&&<p className="error-text">时段重叠：{published.diagnostics.overlaps.map((o:any)=>`${o.from} → ${o.to||'未封口'}`).join('；')}</p>}
   {published.diagnostics?.gaps?.length>0&&<p className="error-text">时段缺口：{published.diagnostics.gaps.map((o:any)=>`${o.from} → ${o.to}`).join('；')}</p>}
   <Table headers={['研究','结论','受影响滤片','原因']}>{(published.diagnostics?.studies||[]).map((s:any)=><tr key={s.study_id}><td>{s.study_name}</td><td>{s.status==='invalidated'?'暂停：出现无法归属的滤片':s.status==='changed'?'需重算':'不受影响'}</td><td>{s.affected_specimens.map((a:any)=>a.specimen_ref).join(', ')||'—'}</td><td>{s.affected_specimens.map((a:any)=>a.reason).filter((v:any,i:any,x:any[])=>x.indexOf(v)===i).join(', ')||'—'}</td></tr>)}</Table>
   {(published.recompute||[]).map((r:any)=><p key={r.run_id}>研究 {r.study_id} 已排队重算：运行 #{r.run_id} / {r.status}{r.error?` / ${r.error}`:''}</p>)}
   {published.blocked_study_ids?.length>0&&<p className="error-text">这些研究含无法唯一归属的滤片，当前结果已停用，修复时段后才可重算：{published.blocked_study_ids.join(', ')}</p>}
  </section>}
  <section className="ledger-section">
   <div className="section-head"><h2>逐片依据与失效原因</h2><span>曲线页可追查每片采取的时段</span></div>
   <label>研究<select value={traceStudyId||''} onChange={e=>setTraceStudyId(+e.target.value)}>{(studies||[]).map((s:any)=><option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
   <button onClick={()=>task.act(async()=>{const result=await sourceApi.trace(traceStudyId||studies?.[0]?.id);setTrace(result)},'已读取逐片校准依据')}>读取逐片依据 →</button>
   {trace&&<><p>{trace.mode==='legacy_raw'?'该研究未绑定仪器：沿用原分析，只使用原始压差。':`仪器 ${trace.calibration?.instrument?.name} / 校准 v${trace.calibration?.version}`}</p>
    {trace.invalid.length>0&&<p className="error-text">失效 {trace.invalid.length} 片：{trace.invalid.map((x:any)=>`${x.specimen_ref}（${x.reason}）`).join('；')}</p>}
    <Table headers={['滤片','测量时刻','原始压差','校正压差','依据时段','倍率 / 零点','失效原因']}>{trace.basis.slice(0,120).map((b:any)=><tr key={b.reading_id}><td>{b.specimen_ref}</td><td>{b.measured_at?clock(b.measured_at):'未记录'}</td><td>{fmt(b.raw_pressure,6)}</td><td>{b.corrected_pressure!=null?fmt(b.corrected_pressure,6):'—'}</td><td>{b.basis?.mode==='legacy_raw'?'沿用原分析':b.basis?`${b.basis.effective_from?.slice(0,10)} → ${b.basis.effective_to?.slice(0,10)||'至今'}`:'—'}</td><td>{b.basis?.mode==='calibrated'?`${b.basis.multiplier} / ${b.basis.offset}`:'—'}</td><td>{b.invalid_reason||'—'}</td></tr>)}</Table></>}
  </section>
 </>;
}
