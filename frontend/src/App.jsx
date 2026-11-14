import { useEffect, useState } from 'react'
import { NavLink, Route, Routes, useLocation } from 'react-router-dom'
import { Activity, ArrowDownToLine, ArrowRight, AudioLines, Bell, BookOpen, Check, ChevronDown, ChevronRight, ClipboardList, Clock3, FileImage, FileText, Fingerprint, FolderOpen, GitBranch, HardDriveUpload, LayoutDashboard, LockKeyhole, LogOut, Menu, MoreHorizontal, Plus, ScanSearch, Search, Settings, ShieldCheck, Sparkles, Upload, X } from 'lucide-react'
import { api } from './api.js'
import { useAuth } from './auth.jsx'
import SignIn from './SignIn.jsx'
import { AuditPage, AuthenticityPage, CasesPage, SettingsPage } from './InvestigationPages.jsx'

const nav = [
  { label: 'Dashboard', path: '/', icon: LayoutDashboard },
  { label: 'Incidents', path: '/cases', icon: FolderOpen },
  { label: 'Evidence Vault', path: '/upload', icon: HardDriveUpload },
  { label: 'Incident Timeline', path: '/timeline', icon: Clock3 },
  { label: 'Relationship Graph', path: '/graph', icon: GitBranch },
  { label: 'AI Summary', path: '/summary', icon: BookOpen },
  { label: 'Authenticity Review', path: '/authenticity', icon: ScanSearch },
  { label: 'Integrity Center', path: '/integrity', icon: ShieldCheck },
  { label: 'Audit Trail', path: '/audit', icon: ClipboardList },
  { label: 'Settings', path: '/settings', icon: Settings },
]
const titles = { '/': 'Dashboard', '/cases': 'Incidents', '/upload': 'Evidence Vault', '/timeline': 'Incident Timeline', '/graph': 'Relationship Graph', '/summary': 'AI Summary', '/authenticity': 'Authenticity Review', '/integrity': 'Integrity Center', '/audit': 'Audit Trail', '/settings': 'Settings' }

function useResource(loader) {
  const [revision, setRevision] = useState(0)
  const [state, setState] = useState({ loading: true, error: null, data: null })
  useEffect(() => {
    let current = true
    setState({ loading: true, error: null, data: null })
    loader().then(data => { if (current) setState({ loading: false, error: null, data }) })
      .catch(error => { if (current) setState({ loading: false, error, data: null }) })
    return () => { current = false }
  }, [loader, revision])
  return { ...state, retry: () => setRevision(value => value + 1) }
}

function Sidebar({ close, email, signOut }) {
  return <aside className="sidebar"><div className="brand"><div className="brand-mark"><Fingerprint size={22}/></div><div><b>Evident<span>AI</span></b><small> DIGITAL EVIDENCE INTELLIGENCE</small></div><button className="mobile-close" onClick={close} aria-label="Close navigation"><X size={19}/></button></div><div className="workspace-label">PRIVATE WORKSPACE</div><div className="case-switch"><span className="case-icon"><FolderOpen size={16}/></span><span className="case-copy"><b>Your investigations</b><small>Authenticated account</small></span></div><div className="nav-label">INVESTIGATION</div><nav>{nav.map(({label,path,icon:Icon})=><NavLink onClick={close} key={path} to={path} end={path==='/'} className={({isActive})=>`nav-link ${isActive?'active':''}`}><Icon size={17}/><span>{label}</span>{label==='Dashboard'&&<span className="nav-dot"/>}</NavLink>)}</nav><div className="sidebar-bottom"><div className="storage"><div className="storage-top"><span>Evidence storage</span><span>PRIVATE</span></div><div className="storage-track"><i className="storage-api"/></div><small>Private Supabase Storage</small></div><button className="profile" onClick={signOut}><div className="avatar"><Activity size={14}/></div><span><b>{email||'Account'}</b><small>Sign out securely</small></span><LogOut size={16}/></button></div></aside>
}

function Header({ title, onMenu, email }) {
  return <header className="topbar"><div className="crumb"><button className="mobile-menu" onClick={onMenu} aria-label="Open navigation"><Menu size={20}/></button><span>Workspace</span><ChevronRight size={14}/><b>{title}</b></div><div className="top-actions"><label className="search-box"><Search size={16}/><input aria-label="Search evidence" placeholder="Search evidence, people, events..."/><kbd>Ã¢Å’Ëœ K</kbd></label><span className="top-profile"><span className="top-avatar"><Activity size={13}/></span><span>{email}</span></span></div></header>
}

function SectionTitle({ eyebrow, title, description, action }) { return <div className="section-title"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{description}</p></div>{action}</div> }
function LoadingState({ label = 'Loading dataÃ¢â‚¬Â¦' }) { return <div className="data-state" role="status"><span className="loading-spinner"/><span>{label}</span></div> }
function ErrorState({ error, retry }) { return <div className="data-state error-state" role="alert"><span>{error?.message || 'Unable to load data.'}</span>{retry&&<button className="inline-link" onClick={retry}>Try again <ArrowRight size={13}/></button>}</div> }
function EmptyState({ title, description, icon: Icon = FolderOpen }) { return <div className="data-state empty-data"><span className="empty-data-icon"><Icon size={17}/></span><b>{title}</b><span>{description}</span></div> }
function recordsFrom(resource) { return Array.isArray(resource.data?.items) ? resource.data.items : Array.isArray(resource.data) ? resource.data : [] }

function Dashboard() {
  const metrics=useResource(api.dashboard)
  const activity=useResource(api.timeline)
  const summary=useResource(api.summary)
  const evidence=useResource(api.evidence)
  const items=recordsFrom(evidence)
  const events=Array.isArray(activity.data?.events)?activity.data.events:[]
  const analysisAvailable=Boolean(summary.data?.summary)
  const metric=(field)=>metrics.data?.[field] ?? 'Ã¢â‚¬â€'
  return <><section className="hero"><div className="hero-copy"><div className="eyebrow"><span className="live-dot"/> INVESTIGATION WORKSPACE</div><h1>Evidence Intelligence,<br/><span>Simplified.</span></h1><p>Bring every signal into focus. Review evidence and investigation activity in one workspace.</p><NavLink className="button button-primary" to="/upload"><Plus size={17}/> Upload Evidence <ArrowRight size={15}/></NavLink></div><div className="hero-art" aria-hidden="true"><div className="art-orbit orbit-one"/><div className="art-orbit orbit-two"/><div className="art-center"><Fingerprint size={51}/></div><span className="art-chip chip-one"><ShieldCheck size={14}/> Evidence review</span><span className="art-chip chip-two"><Activity size={14}/> Intelligence</span><span className="art-node node-one"/><span className="art-node node-two"/><span className="art-node node-three"/></div><div className="hero-case"><span className="case-symbol"><FolderOpen size={16}/></span><span><small>INVESTIGATION WORKSPACE</small><b>{metrics.loading?'Loading evidence workspaceÃ¢â‚¬Â¦':`${metric('evidence_items')} evidence items available`}</b></span></div></section>
    <div className="stats-grid"><Stat icon={FileText} label="Total evidence" value={metrics.loading?'Ã¢â‚¬Â¦':metric('evidence_items')} note="Uploaded evidence" tint="blue"/><Stat icon={FolderOpen} label="Active cases" value={metrics.loading?'Ã¢â‚¬Â¦':metric('active_investigations')} note="Cases connected" tint="slate"/><Stat icon={Activity} label="Events identified" value={metrics.loading?'Ã¢â‚¬Â¦':metric('events_identified')} note="From completed analyses" tint="purple"/><Stat icon={ShieldCheck} label="Integrity verified" value={metrics.loading?'Ã¢â‚¬Â¦':metrics.data?.integrity_verified_percent != null?`${metrics.data.integrity_verified_percent}%`:'Ã¢â‚¬â€'} note="Run checks in Integrity Center" tint="green"/>{metrics.error&&<div className="stats-error"><ErrorState error={metrics.error} retry={metrics.retry}/></div>}</div>
    <div className="content-grid"><section className="panel insights-panel"><div className="panel-heading"><div><div className="panel-kicker purple-text"><Sparkles size={13}/> INTELLIGENCE BRIEF</div><h2>AI summary</h2><p>Generated from analyzed evidence</p></div><span className="ai-badge">AI POWERED</span></div>{summary.loading?<LoadingState label="Loading analysisÃ¢â‚¬Â¦"/>:summary.error?<ErrorState error={summary.error} retry={summary.retry}/>:analysisAvailable?<><div className="insight-card primary-insight"><div className="insight-icon purple"><Sparkles size={16}/></div><div><span className="insight-label">EVIDENCE SUMMARY</span><h3>{summary.data.summary}</h3><p>{(summary.data.concerns||[]).length?`${summary.data.concerns.length} concern${summary.data.concerns.length===1?'':'s'} identified across analyzed evidence.`:'No concerns reported in current analysis.'}</p><NavLink className="inline-link" to="/summary">View full analysis <ArrowRight size={14}/></NavLink></div></div></>:<EmptyState icon={Sparkles} title="No AI analysis available" description="Upload and analyze evidence to generate findings."/>}<div className="insights-foot"><span>Analysis data from FastAPI</span><NavLink to="/summary">Open AI summary <ArrowRight size={14}/></NavLink></div></section>
      <section className="panel activity-panel"><div className="panel-heading"><div><div className="panel-kicker">EVIDENCE ACTIVITY</div><h2>Recent events</h2><p>Events from completed analyses</p></div><button className="icon-button" aria-label="Activity feed"><MoreHorizontal size={19}/></button></div>{activity.loading?<LoadingState label="Loading recent activityÃ¢â‚¬Â¦"/>:activity.error?<ErrorState error={activity.error} retry={activity.retry}/>:events.length?<div className="activity-feed">{events.slice(0,5).map((event,index)=><EventRow key={`${event.evidence_id||''}-${index}`} event={event} index={index}/>)}</div>:<EmptyState icon={Activity} title="No timeline events available" description="Analyze evidence to add events to this feed."/>}<NavLink className="activity-footer" to="/timeline">View incident timeline <ArrowRight size={15}/></NavLink></section></div>
    <section className="panel investigations"><div className="panel-heading"><div><div className="panel-kicker">EVIDENCE VAULT</div><h2>Recently uploaded evidence</h2><p>Files stored by the backend</p></div><NavLink className="text-button" to="/upload">Open vault <ArrowRight size={15}/></NavLink></div>{evidence.loading?<LoadingState label="Loading evidenceÃ¢â‚¬Â¦"/>:evidence.error?<ErrorState error={evidence.error} retry={evidence.retry}/>:items.length?<EvidenceList items={items.slice(0,5)}/>:<EmptyState icon={FileText} title="No evidence uploaded yet" description="Upload a file to begin an investigation."/>}</section><footer className="page-foot"><span><LockKeyhole size={13}/> Evidence and analysis are served by your backend</span><span>Workspace data <i/></span></footer></>
}

function Stat({icon:Icon,label,value,note,tint}) { return <div className="stat-card"><div className={`stat-icon ${tint}`}><Icon size={18}/></div><span className="stat-label">{label}</span><b className="stat-value">{value}</b><div className="stat-note">{note}</div></div> }
function formatSize(bytes=0) { return bytes<1024*1024?`${Math.max(1,Math.round(bytes/1024))} KB`:`${(bytes/(1024*1024)).toFixed(1)} MB` }
function categoryIcon(category) { return category==='image'?FileImage:category==='audio'?AudioLines:FileText }
function EvidenceList({items,onAnalyze,analyzingId}) { return <div className="evidence-list">{items.map((item,index)=>{const Icon=categoryIcon(item.file_type);return <div className="evidence-row" key={item.evidence_id||index}><div className={`file-icon ${item.file_type==='image'?'purple':item.file_type==='audio'?'amber':'blue'}`}><Icon size={17}/></div><div className="file-name"><b>{item.original_filename||'Evidence file'}</b><small>{(item.file_type||'file').toUpperCase()} Ã‚Â· {formatSize(item.file_size||0)} Ã‚Â· SHA-256 {item.sha256_hash?`${item.sha256_hash.slice(0,12)}Ã¢â‚¬Â¦`:'pending'}</small>{item.duplicate_of&&<small className="duplicate-notice">Exact duplicate of {item.duplicate_of}</small>}{item.processing_error&&<small className="processing-error">{item.processing_error}</small>}</div><span className="file-time">{item.processing_status==='processed'?'Processed':item.processing_status==='failed'?'Failed':item.processing_status==='processing'?'Processing':'Uploaded'}</span>{onAnalyze&&<button className="row-action" disabled={analyzingId===item.evidence_id} onClick={()=>onAnalyze(item)}>{analyzingId===item.evidence_id?'AnalyzingÃ¢â‚¬Â¦':item.analysis?'Re-analyze':'Analyze'}</button>}</div>})}</div> }
function EventRow({event,index}) { const colors=['blue','purple','amber'];const when=event.date_or_time||event.timestamp||event.time||'';const label=event.description||event.title||event.name||'Timeline event';return <div className="event"><div className={`event-mark ${colors[index%colors.length]}`}><i/></div><div className="event-content"><div className="event-meta"><small>{when||'Date/time not specified'}</small><em className={colors[index%colors.length]}>{event.original_filename||'ANALYZED EVIDENCE'}</em></div><b>{label}</b><span>{event.evidence_id?`Evidence ID ${event.evidence_id}`:''}</span></div></div> }

function UploadPage() {
  const evidence=useResource(api.evidence)
  const cases=useResource(api.cases)
  const [incidentId,setIncidentId]=useState('')
  const [caseTitle,setCaseTitle]=useState('')
  const [caseError,setCaseError]=useState(null)
  const [creatingCase,setCreatingCase]=useState(false)
  const [drag,setDrag]=useState(false)
  const [files,setFiles]=useState([])
  const [uploading,setUploading]=useState(false)
  const [uploadProgress,setUploadProgress]=useState(0)
  const [currentFile,setCurrentFile]=useState('')
  const [uploadError,setUploadError]=useState(null)
  const [analyzeError,setAnalyzeError]=useState(null)
  const [analyzingId,setAnalyzingId]=useState(null)
  const [latestAnalysis,setLatestAnalysis]=useState(null)
  const records=recordsFrom(evidence)
  const caseRows=Array.isArray(cases.data?.cases)?cases.data.cases:[]
  const activeCases=caseRows.filter(item=>item.status==='active')
  useEffect(()=>{if(!incidentId&&caseRows.length)setIncidentId(activeCases[0]?.id||'')},[caseRows,incidentId])
  const add=(list)=>{setFiles(value=>[...value,...Array.from(list)]);setUploadError(null)}
  const createCase=async(event)=>{
    event.preventDefault();setCreatingCase(true);setCaseError(null)
    try{const result=await api.createCase({title:caseTitle});const created=result.case;cases.retry();setIncidentId(created.id);setCaseTitle('')}
    catch(error){setCaseError(error)}finally{setCreatingCase(false)}
  }
  const submit=async()=>{
    if(!files.length)return
    if(!incidentId){setUploadError(new Error('Create or select an incident before uploading evidence.'));return}
    setUploading(true);setUploadError(null)
    for(const file of files){
      setCurrentFile(file.name);setUploadProgress(0)
      try{await api.uploadEvidence(file,incidentId,setUploadProgress);setFiles(value=>value.filter(item=>item!==file))}
      catch(error){setUploadError(error);break}
    }
    setUploading(false);setCurrentFile('');evidence.retry()
  }
  const analyze=async(item)=>{
    setAnalyzingId(item.evidence_id);setAnalyzeError(null);setLatestAnalysis(null)
    try{const result=await api.analyzeEvidence(item.evidence_id);setLatestAnalysis(result);evidence.retry()}
    catch(error){setAnalyzeError(error);evidence.retry()}
    finally{setAnalyzingId(null)}
  }
  return <><SectionTitle eyebrow="SECURE EVIDENCE INTAKE" title="Evidence Vault" description="Upload, analyze, and verify evidence within an incident you own."/>
    <section className="panel incident-select"><label htmlFor="incident-select"><b>Incident for this upload</b><small>Every evidence item is linked to the selected incident.</small></label>{cases.loading?<LoadingState label="Loading your incidentsâ€¦"/>:cases.error?<ErrorState error={cases.error} retry={cases.retry}/>:caseRows.length?<select id="incident-select" value={incidentId} onChange={event=>setIncidentId(event.target.value)}>{activeCases.map(item=><option key={item.id} value={item.id}>{item.incident_number} Â· {item.title}</option>)}</select>:<span className="case-empty">Create an incident below before uploading evidence.</span>}</section>
    {!cases.loading&&activeCases.length===0&&<form className="panel create-case-inline" onSubmit={createCase}><label htmlFor="new-incident-title">New incident title</label><input id="new-incident-title" value={caseTitle} onChange={event=>setCaseTitle(event.target.value)} maxLength={200} required placeholder="Describe this investigation"/><button className="button button-primary" disabled={creatingCase||!caseTitle.trim()}>{creatingCase?'Creatingâ€¦':'Create incident'} <ArrowRight size={15}/></button>{caseError&&<ErrorState error={caseError}/>}</form>}
    <div className="vault-toolbar"><div><b>Evidence records</b><span>{evidence.loading?'Loadingâ€¦':`${records.length} stored`}</span></div><button className="button button-secondary" disabled><ArrowDownToLine size={15}/> Export register</button></div>
    <section className="panel vault-list">{evidence.loading?<LoadingState label="Loading evidence recordsâ€¦"/>:evidence.error?<ErrorState error={evidence.error} retry={evidence.retry}/>:records.length?<EvidenceList items={records} onAnalyze={analyze} analyzingId={analyzingId}/>:<EmptyState icon={FileText} title="No evidence uploaded yet" description="Select or drop a supported file below to create the first evidence record."/>}</section>
    {analyzeError&&<div className="panel action-error"><ErrorState error={analyzeError} retry={()=>evidence.retry()}/></div>}{latestAnalysis&&<AnalysisResult result={latestAnalysis} compact/>}
    <div className="upload-layout"><label className={`dropzone ${drag?'drag':''}`} onDragOver={event=>{event.preventDefault();setDrag(true)}} onDragLeave={()=>setDrag(false)} onDrop={event=>{event.preventDefault();setDrag(false);add(event.dataTransfer.files)}}><input type="file" multiple accept=".pdf,.jpg,.jpeg,.png,.txt,.csv,.mp3,.wav,.m4a" onChange={event=>{add(event.target.files);event.target.value=''}}/><div className="upload-icon"><Upload size={22}/></div><b>Drop evidence files here</b><span>or <strong>browse files</strong> from your device</span><small>PDF, image, text/CSV, and audio Â· Up to 200 MB per file</small></label><div className="panel upload-side"><div className="panel-kicker">SECURE INTAKE</div><h2>Preserve evidence integrity</h2><p>Original bytes are hashed at intake and retained in a private Supabase Storage bucket.</p><div className="secure-line"><Check size={15}/> SHA-256 integrity hash at intake</div><div className="secure-line"><Check size={15}/> Original file stored privately</div><div className="secure-line"><Check size={15}/> Processing can be retried after failure</div></div></div>
    {files.length>0&&<section className="panel queue"><h2>Ready to upload <span>{files.length}</span></h2>{files.map((file,index)=><div key={`${file.name}-${index}`} className="queue-file"><FileText size={16}/>{file.name}<span>{formatSize(file.size)}</span></div>)}{uploadError&&<ErrorState error={uploadError} />}{uploading&&<div className="upload-progress"><span>{currentFile}</span><div className="storage-track"><i style={{width:`${uploadProgress}%`}}/></div><small>{uploadProgress}%</small></div>}<button className="button button-primary" disabled={uploading||!incidentId} onClick={submit}>{uploading?'Uploadingâ€¦':'Upload evidence'} <ArrowRight size={15}/></button></section>}
  </>
}
function AnalysisResult({result,compact=false}) { return <section className={`panel analysis-result ${compact?'compact':''}`}><div className="panel-heading"><div><div className="panel-kicker purple-text"><Sparkles size={13}/> ANALYSIS COMPLETE</div><h2>{result.original_filename}</h2></div><NavLink className="text-button" to="/summary">Open full summary <ArrowRight size={14}/></NavLink></div><p className="analysis-result-summary">{result.analysis?.summary}</p><div className="analysis-tags">{(result.analysis?.people||[]).slice(0,5).map(value=><span key={`p-${value}`}>{value}</span>)}{(result.analysis?.locations||[]).slice(0,4).map(value=><span key={`l-${value}`}>{value}</span>)}</div></section> }

function DataPage({path}) {
  const loaders={'/timeline':api.timeline,'/graph':api.graph,'/summary':api.summary}
  const resource=useResource(loaders[path])
  const data=resource.data||{}
  const events=Array.isArray(data.events)?[...data.events].sort(compareEvents):[]
  const nodes=Array.isArray(data.nodes)?data.nodes:[]
  const edges=Array.isArray(data.edges)?data.edges:[]
  const hasSummary=Boolean(data.summary||data.people?.length||data.locations?.length||data.events?.length||data.concerns?.length)
  const config={
    '/timeline':['EVENT SEQUENCE','Review events in chronological order.','No timeline events available','Analyze evidence to add events to this timeline.',Clock3],
    '/graph':['ENTITY RELATIONSHIPS','Explore people, locations, events, and their source evidence.','No relationships found','Analyze evidence to create relationship nodes and connections.',GitBranch],
    '/summary':['AI GENERATED BRIEF','Structured analysis returned by Gemini.','AI summary will appear after evidence analysis','Upload and analyze evidence to generate a summary.',Sparkles],
  }[path]
  const empty=path==='/timeline'?!events.length:path==='/graph'?!nodes.length:path==='/summary'?!hasSummary:false
  return <><SectionTitle eyebrow={config[0]} title={titles[path]} description={config[1]}/><div className="panel data-page-panel">{resource.loading?<LoadingState label={`Loading ${titles[path].toLowerCase()}Ã¢â‚¬Â¦`}/>:resource.error?<ErrorState error={resource.error} retry={resource.retry}/>:empty?<EmptyState icon={config[4]} title={config[2]} description={config[3]}/>:path==='/timeline'?<div className="activity-feed timeline-feed">{events.map((event,index)=><EventRow key={`${event.evidence_id||''}-${index}`} event={event} index={index}/>)}</div>:path==='/graph'?<GraphData nodes={nodes} edges={edges}/>:<SummaryData data={data}/>}</div></>
}

function compareEvents(a,b) { const left=Date.parse(a.date_or_time||'');const right=Date.parse(b.date_or_time||'');if(Number.isNaN(left)&&Number.isNaN(right))return String(a.date_or_time||'').localeCompare(String(b.date_or_time||''));if(Number.isNaN(left))return 1;if(Number.isNaN(right))return -1;return left-right }
function SummaryData({data}) { return <div className="summary-content"><div className="panel-kicker purple-text"><Sparkles size={13}/> AI SUMMARY</div><h2>Evidence overview</h2><p>{data.summary||'No summary returned.'}</p>{data.evidence_count!=null&&<small>Built from {data.evidence_count} analyzed evidence item(s)</small>}<SummaryList title="People" values={data.people}/><SummaryList title="Locations" values={data.locations}/><SummaryList title="Dates and times" values={data.dates}/><SummaryList title="Events" values={(data.events||[]).map(event=>`${event.date_or_time||'Time not specified'} Ã¢â‚¬â€ ${event.description}`)}/><SummaryList title="Concerns" values={data.concerns}/></div> }
function SummaryList({title,values=[]}) { if(!values.length)return null;return <section className="summary-list"><h3>{title}</h3><ul>{values.map((value,index)=><li key={`${title}-${index}`}>{value}</li>)}</ul></section> }
function GraphData({nodes,edges}) {
  const visibleNodes=nodes.slice(0,14)
  const center={x:380,y:205}
  const radius=visibleNodes.length>8?165:130
  const points=new Map(visibleNodes.map((node,index)=>{const angle=(Math.PI*2*index/Math.max(visibleNodes.length,1))-(Math.PI/2);return[node.id,{x:visibleNodes.length===1?center.x:center.x+Math.cos(angle)*radius,y:visibleNodes.length===1?center.y:center.y+Math.sin(angle)*radius}]}))
  const links=edges.filter(edge=>points.has(edge.source)&&points.has(edge.target))
  return <div className="graph-wrap"><div className="panel-heading"><div><h2>Evidence relationship map</h2><p>{nodes.length} entities Ã‚Â· {edges.length} evidence links</p></div></div><svg className="relationship-graph" viewBox="0 0 760 410" role="img" aria-label="Evidence relationship graph">{links.map(edge=>{const from=points.get(edge.source);const to=points.get(edge.target);return <line key={edge.id||`${edge.source}-${edge.target}`} x1={from.x} y1={from.y} x2={to.x} y2={to.y} className="graph-edge"/>})}{visibleNodes.map(node=>{const point=points.get(node.id);return <g key={node.id} transform={`translate(${point.x-64} ${point.y-27})`}><title>{node.type}: {node.label}</title><rect width="128" height="54" rx="9" className={`graph-node graph-${node.type||'entity'}`}/><text x="64" y="23" textAnchor="middle" className="graph-label">{(node.label||'Entity').slice(0,19)}{(node.label||'').length>19?'Ã¢â‚¬Â¦':''}</text><text x="64" y="40" textAnchor="middle" className="graph-type">{node.type||'entity'}</text></g>})}</svg>{nodes.length>visibleNodes.length&&<small className="graph-note">Showing {visibleNodes.length} of {nodes.length} entities.</small>}</div>
}

function IntegrityPage() {
  const evidence=useResource(api.evidence)
  const [checking,setChecking]=useState(null)
  const [results,setResults]=useState({})
  const [error,setError]=useState(null)
  const records=recordsFrom(evidence)
  const verify=async(item)=>{setChecking(item.evidence_id);setError(null);try{const result=await api.verifyEvidence(item.evidence_id);setResults(value=>({...value,[item.evidence_id]:result}))}catch(err){setError(err)}finally{setChecking(null)}}
  return <><SectionTitle eyebrow="CHAIN OF CUSTODY" title="Integrity Center" description="Recalculate the SHA-256 digest and compare it with the value captured at upload."/><div className="panel data-page-panel integrity-page">{evidence.loading?<LoadingState label="Loading evidence integrity recordsÃ¢â‚¬Â¦"/>:evidence.error?<ErrorState error={evidence.error} retry={evidence.retry}/>:records.length?<><div className="integrity-overview"><div><span>Evidence items</span><b>{records.length}</b></div><div><span>Algorithm</span><b>SHA-256</b></div><div><span>Latest result</span><b>{Object.values(results).some(item=>!item.verified)?'Review required':Object.keys(results).length?'Verified':'Not checked'}</b></div></div>{error&&<ErrorState error={error}/>}<div className="integrity-records">{records.map(item=><IntegrityRecord key={item.evidence_id} item={item} result={results[item.evidence_id]} checking={checking===item.evidence_id} onVerify={()=>verify(item)}/>)}</div></>:<EmptyState icon={ShieldCheck} title="No integrity records available" description="Upload evidence to create a SHA-256 integrity record."/>}</div></>
}
function IntegrityRecord({item,result,checking,onVerify}) { return <article className="integrity-record"><div className="integrity-record-head"><div><b>{item.original_filename}</b><small>{item.evidence_id}</small></div><button className="button button-secondary" disabled={checking} onClick={onVerify}>{checking?'VerifyingÃ¢â‚¬Â¦':'Re-verify'}</button></div><div className="hash-line"><span>Original SHA-256</span><code>{item.sha256_hash||'Unavailable'}</code></div>{result&&<><div className="hash-line"><span>Current SHA-256</span><code>{result.current_sha256_hash}</code></div><div className={`integrity-result ${result.verified?'is-verified':'is-mismatch'}`}><span>{result.verified?'Hash verified':'Hash mismatch'}</span><small>Checked {new Date(result.checked_at).toLocaleString()}</small></div></>}</article> }

function App() {
  const auth=useAuth()
  const location=useLocation()
  const [open,setOpen]=useState(false)
  const [profileAttempt,setProfileAttempt]=useState(0)
  const [profileSetup,setProfileSetup]=useState({userId:null,loading:false,error:null})
  const userId=auth.session?.user?.id
  useEffect(()=>{
    if(!userId)return undefined
    let active=true
    setProfileSetup({userId,loading:true,error:null})
    api.bootstrapProfile().then(()=>{if(active)setProfileSetup({userId,loading:false,error:null})})
      .catch(error=>{if(active)setProfileSetup({userId,loading:false,error})})
    return ()=>{active=false}
  },[userId,profileAttempt])
  if(auth.loading)return <div className="auth-screen"><LoadingState label="Restoring secure sessionâ€¦"/></div>
  if(!auth.session)return <SignIn/>
  if(profileSetup.userId!==userId||profileSetup.loading)return <div className="auth-screen"><LoadingState label="Preparing your private profile…"/></div>
  if(profileSetup.error)return <div className="auth-screen"><section className="auth-card" role="alert"><h1>Profile setup failed</h1><p>{profileSetup.error.message||'Your account profile could not be prepared.'}</p><button className="button button-primary" onClick={()=>setProfileAttempt(value=>value+1)}>Retry profile setup</button><button className="auth-toggle" onClick={auth.signOut}>Sign out</button></section></div>
  const email=auth.session.user?.email||'Account'
  const title=titles[location.pathname]||'Dashboard'
  return <div className="app-shell"><div className={'sidebar-wrap '+(open?'show':'')}><Sidebar close={()=>setOpen(false)} email={email} signOut={auth.signOut}/></div>{open&&<button className="scrim" onClick={()=>setOpen(false)} aria-label="Close navigation"/>}<main className="main"><Header title={title} email={email} onMenu={()=>setOpen(true)}/><div className="page"><Routes><Route path="/" element={<Dashboard/>}/><Route path="/cases" element={<CasesPage/>}/><Route path="/upload" element={<UploadPage/>}/><Route path="/timeline" element={<DataPage path="/timeline"/>}/><Route path="/graph" element={<DataPage path="/graph"/>}/><Route path="/summary" element={<DataPage path="/summary"/>}/><Route path="/authenticity" element={<AuthenticityPage/>}/><Route path="/integrity" element={<IntegrityPage/>}/><Route path="/audit" element={<AuditPage/>}/><Route path="/settings" element={<SettingsPage email={email}/>}/></Routes></div></main></div>
}

export default App
