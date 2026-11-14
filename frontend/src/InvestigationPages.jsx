import { useEffect, useState } from 'react'
import { ArrowRight, ClipboardList, Plus, ScanSearch } from 'lucide-react'
import { api } from './api.js'

function SectionTitle({ eyebrow, title, description }) {
  return <div className="section-title"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{description}</p></div></div>
}
function Loading() { return <div className="data-state" role="status">Loading…</div> }
function ErrorBox({ error, retry }) { return <div className="data-state error-state" role="alert">{error?.message||'Unable to load data.'} <button className="inline-link" onClick={retry}>Try again <ArrowRight size={13}/></button></div> }

export function CasesPage() {
  const [revision, setRevision] = useState(0)
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const load = async () => {
    setLoading(true); setError(null)
    try { setData(await api.cases()) } catch (err) { setError(err) } finally { setLoading(false) }
  }
  // Load after mount and after case creation.
  useEffect(() => { load() }, [])
  const refresh = () => { setRevision(value => value + 1); load() }
  const cases = Array.isArray(data?.cases) ? data.cases : []
  const create = async event => {
    event.preventDefault(); setBusy(true); setError(null)
    try { await api.createCase({ title, description: description || null }); setTitle(''); setDescription(''); refresh() }
    catch (err) { setError(err) } finally { setBusy(false) }
  }
  return <><SectionTitle eyebrow="INCIDENT MANAGEMENT" title="Your incidents" description="Incidents are private to your authenticated account. Evidence uploads must belong to an active incident."/>
    <form className="panel case-create-form" onSubmit={create}><h2>Create an incident</h2><label>Title<input value={title} onChange={event=>setTitle(event.target.value)} maxLength={200} required/></label><label>Description (optional)<textarea value={description} onChange={event=>setDescription(event.target.value)} maxLength={4000}/></label>{error&&<ErrorBox error={error} retry={refresh}/>}<button className="button button-primary" disabled={busy||!title.trim()}>{busy?'Saving…':'Create incident'} <Plus size={15}/></button></form>
    <section className="panel case-list-panel"><div className="panel-heading"><div><div className="panel-kicker">PRIVATE CASES</div><h2>Incident register</h2></div><span>{cases.length} incident{cases.length===1?'':'s'}</span></div>{loading?<Loading/>:error?<ErrorBox error={error} retry={refresh}/>:cases.length?<div className="incident-list">{cases.map(item=><article key={item.id} className="incident-card"><div><small>{item.incident_number}</small><b>{item.title}</b>{item.description&&<p>{item.description}</p>}</div><span className={`status ${item.status==='active'?'':'review'}`}><i/>{item.status}</span></article>)}</div>:<div className="data-state empty-data"><b>No incidents yet</b><span>Create an incident before uploading evidence.</span></div>}</section></>
}

export function AuthenticityPage() {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [active, setActive] = useState(null)
  const [assessment, setAssessment] = useState(null)
  const load = async () => {
    setLoading(true); setError(null)
    try { const result=await api.evidence(); setItems(result.items||[]) } catch (err) { setError(err) } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])
  const assess = async item => {
    setActive(item.evidence_id); setError(null); setAssessment(null)
    try { setAssessment(await api.assessAuthenticity(item.evidence_id)); await load() } catch (err) { setError(err) } finally { setActive(null) }
  }
  return <><SectionTitle eyebrow="FORENSIC REVIEW" title="Evidence Authenticity Assessment" description="Review observable file metadata and limitations. Automated indicators do not prove whether evidence is genuine or fraudulent."/><div className="authenticity-disclaimer">Automated assessment only. This result is not a legal determination of authenticity or fraud.</div>
    <section className="panel data-page-panel">{loading?<Loading/>:error?<ErrorBox error={error} retry={load}/>:items.length?<div className="authenticity-records">{items.map(item=><article className="authenticity-record" key={item.evidence_id}><div><b>{item.original_filename}</b><small>{item.evidence_id} · {item.authenticity_classification||'NOT ASSESSED'}</small></div><button className="button button-secondary" disabled={active===item.evidence_id} onClick={()=>assess(item)}>{active===item.evidence_id?'Assessing…':item.authenticity_assessment?'Run again':'Assess file'}</button></article>)}</div>:<div className="data-state empty-data"><ScanSearch size={18}/><b>No evidence to assess</b><span>Upload evidence to inspect measurable file metadata.</span></div>}</section>
    {error&&<div className="panel action-error"><ErrorBox error={error} retry={load}/></div>}{assessment&&<section className="panel assessment-result"><div className="panel-kicker">ASSESSMENT · {assessment.classification}</div><p>Confidence: {Math.round((assessment.confidence||0)*100)}% (the available signals do not support a genuine/fraud verdict).</p><p>{assessment.limitations?.[0]}</p><h3>Observed indicators</h3>{assessment.signals?.length?<ul>{assessment.signals.map((signal,index)=><li key={index}><b>{signal.severity}</b> · {signal.description}</li>)}</ul>:<p>No alteration or AI-generation indicators were measured by the available checks.</p>}<h3>Integrity</h3><p>{assessment.integrity_information?.status||'NOT VERIFIED'} · A matching SHA-256 hash confirms the stored bytes match upload time; it does not prove source authenticity.</p><details><summary>Metadata collected</summary><pre>{JSON.stringify(assessment.metadata_analysis||{},null,2)}</pre></details><h3>Limitations</h3><ul>{(assessment.limitations||[]).map((item,index)=><li key={index}>{item}</li>)}</ul><h3>Human verification steps</h3><ul>{(assessment.recommended_verification||[]).map((item,index)=><li key={index}>{item}</li>)}</ul></section>}</>
}

export function AuditPage() {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const load = async () => { setLoading(true); setError(null); try { const result=await api.audit(); setItems(result.items||[]) } catch (err) { setError(err) } finally { setLoading(false) } }
  useEffect(() => { load() }, [])
  return <><SectionTitle eyebrow="CHAIN OF CUSTODY" title="Audit Trail" description="Per-user SHA-256 hash chaining makes edits detectable. It does not make the system physically tamper-proof."/><section className="panel data-page-panel">{loading?<Loading/>:error?<ErrorBox error={error} retry={load}/>:items.length?<div className="audit-list">{items.map(item=><article key={item.id} className="audit-row"><div><b>{item.action.replaceAll('_',' ')}</b><small>{item.resource_type}{item.resource_id?` · ${item.resource_id}`:''}</small><time>{new Date(item.created_at).toLocaleString()}</time></div><code title={item.current_hash}>SHA-256 {item.current_hash?.slice(0,16)}…</code></article>)}</div>:<div className="data-state empty-data"><ClipboardList size={18}/><b>No audit actions yet</b><span>New incident and evidence operations will appear here.</span></div>}</section></>
}

export function SettingsPage({ email }) {
  return <><SectionTitle eyebrow="ACCOUNT" title="Settings" description="Account and service configuration for this workspace."/><section className="panel data-page-panel"><div className="summary-list"><h3>Signed-in account</h3><p>{email}</p></div><div className="summary-list"><h3>Authentication</h3><p>Supabase Auth session. Private API requests use the session bearer token.</p></div><div className="summary-list"><h3>Evidence storage</h3><p>Private Supabase Storage bucket; only the backend service key accesses stored originals.</p></div><div className="summary-list"><h3>External AI processing</h3><p>Evidence text is sent to Gemini for structured analysis after extraction. The original file remains stored separately.</p></div></section></>
}
