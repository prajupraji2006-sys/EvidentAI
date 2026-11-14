import { useState } from 'react'
import { Fingerprint, LockKeyhole } from 'lucide-react'
import { supabase, useAuth } from './auth.jsx'
import { api } from './api.js'

export default function SignIn() {
  const { configured } = useAuth()
  const [mode, setMode] = useState('sign-in')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    setError('')
    setMessage('')
    try {
      const result = mode === 'sign-in'
        ? await supabase.auth.signInWithPassword({ email: email.trim(), password })
        : await supabase.auth.signUp({ email: email.trim(), password })
      if (result.error) throw result.error
      if (result.data.session) {
        api.recordLogin().catch(() => {})
      }
      if (mode === 'sign-up') {
        setMessage(result.data.session
          ? 'Your account was created successfully.'
          : 'Check your email to confirm your account, then sign in.')
      }
    } catch (err) {
      console.error('EvidentAI authentication request failed:', {
        name: err?.name,
        message: err?.message,
        status: err?.status,
        code: err?.code,
      })
      setError('Unable to complete authentication. Please check your email and password and try again.')
    } finally {
      setBusy(false)
    }
  }

  return <main className="auth-screen"><section className="auth-card">
    <div className="auth-brand"><span className="brand-mark"><Fingerprint size={24}/></span><div><b>Evident<span>AI</span></b><small>PRIVATE INVESTIGATION WORKSPACE</small></div></div>
    {!configured ? <div className="auth-message" role="alert"><b>Authentication is not configured.</b><p>Set VITE_SUPABASE_URL and VITE_SUPABASE_PUBLISHABLE_KEY in frontend/.env.local, then restart Vite.</p></div> : <>
      <div className="panel-kicker"><LockKeyhole size={13}/> SECURE ACCESS</div><h1>{mode === 'sign-in' ? 'Sign in to EvidentAI' : 'Create your account'}</h1>
      <p className="auth-copy">Evidence and incident data are available only to your authenticated account.</p>
      <form onSubmit={submit} className="auth-form"><label>Email<input type="email" autoComplete="email" required value={email} onChange={event=>setEmail(event.target.value)}/></label><label>Password<input type="password" minLength={8} autoComplete={mode === 'sign-in' ? 'current-password' : 'new-password'} required value={password} onChange={event=>setPassword(event.target.value)}/></label>
        {error&&<div className="auth-error" role="alert">{error}</div>}{message&&<div className="auth-message" role="status">{message}</div>}
        <button className="button button-primary auth-submit" disabled={busy}>{busy?'Please wait…':mode==='sign-in'?'Sign in':'Create account'}</button>
      </form>
      <button className="auth-toggle" onClick={()=>{setMode(mode==='sign-in'?'sign-up':'sign-in');setError('');setMessage('')}}>{mode==='sign-in'?"Need an account? Sign up":"Already registered? Sign in"}</button>
      <small className="auth-legal">Your account is managed by Supabase Auth. An email confirmation may be required.</small>
    </>}
  </section></main>
}
