import React, { useState, useEffect, useRef } from 'react';
import {
  Mic, Video, MessageSquare, Brain, Sparkles,
  Upload, Languages, Loader2, Zap, RefreshCw,
  History, X, Activity, ChevronDown, ArrowRight
} from 'lucide-react';
import './styles.css';

const API_URL = '';

const LANGUAGES = [
  'english','hindi','bengali','tamil','telugu',
  'marathi','kannada','malayalam','french','german',
  'spanish','portuguese','italian'
];

const MODES = [
  { id:'text',    label:'Text',    sub:'Translation', icon:MessageSquare, color:'blue'   },
  { id:'context', label:'Context', sub:'Aware',       icon:Brain,         color:'purple' },
  { id:'audio',   label:'Speech',  sub:'to Text',     icon:Mic,           color:'green'  },
  { id:'video',   label:'Video',   sub:'to Text',     icon:Video,         color:'red'    },
  { id:'emotion', label:'Emotion', sub:'Detection',   icon:Sparkles,      color:'pink'   },
];

const EMOTION_COLORS = {
  joy:'#22c55e', sadness:'#3b82f6', anger:'#ef4444',
  fear:'#a855f7', surprise:'#f59e0b', disgust:'#f97316', neutral:'#94a3b8',
};
const EMOTION_ICONS = {
  joy:'😊', sadness:'😢', anger:'😠',
  fear:'😨', surprise:'😲', disgust:'🤢', neutral:'😐',
};

// ── Per-mode isolated state — fixes the carry-over bug ──────
const EMPTY_MODE_STATE = {
  sourceText:    '',
  translatedText:'',
  emotion:       null,
  perf:          null,
  mediaURL:      null,
  mediaType:     null,
  fileName:      null,
  context:       [],
  ctxInfluence:  0,
};

export default function TranslationApp() {
  const [mode, setMode]         = useState('text');
  const [sourceLang, setSource] = useState('english');
  const [targetLang, setTarget] = useState('hindi');
  const [useContext, setUseCtx] = useState(false);
  const [loading, setLoading]   = useState(false);
  const [sessionId, setSessId]  = useState(null);
  const [history, setHistory]   = useState([]);
  const [showHistory, setShowH] = useState(false);
  const [visibleWords, setVW]   = useState(0);
  const [animating, setAnim]    = useState(false);

  // ── Each mode has its OWN isolated state ──────────────────
  const [modeStates, setModeStates] = useState({
    text:    { ...EMPTY_MODE_STATE },
    context: { ...EMPTY_MODE_STATE },
    audio:   { ...EMPTY_MODE_STATE },
    video:   { ...EMPTY_MODE_STATE },
    emotion: { ...EMPTY_MODE_STATE },
  });

  const cur = modeStates[mode]; // current mode's state

  const setModeField = (field, value) => {
    setModeStates(prev => ({
      ...prev,
      [mode]: { ...prev[mode], [field]: value }
    }));
  };

  const fileRef  = useRef(null);
  const timerRef = useRef(null);

  useEffect(() => {
    setSessId('sess_' + Date.now() + '_' + Math.random().toString(36).slice(2,8));
  }, []);

  // Reset animation when mode changes
  useEffect(() => {
    setAnim(false); setVW(0);
  }, [mode]);

  // Word-by-word animation
  useEffect(() => {
    if (!animating || !cur.translatedText) return;
    const words = cur.translatedText.split(' ');
    if (visibleWords >= words.length) { setAnim(false); return; }
    timerRef.current = setTimeout(() => setVW(v => v + 1), 70);
    return () => clearTimeout(timerRef.current);
  }, [animating, visibleWords, cur.translatedText]);

  const handleTranslate = async (file = null) => {
    if (!cur.sourceText && !file) return;
    setLoading(true);
    setModeField('translatedText', '');
    setModeField('emotion', null);
    setModeField('ctxInfluence', 0);
    setVW(0); setAnim(false);

    try {
      const fd = new FormData();
      fd.append('source_lang', sourceLang);
      fd.append('target_lang', targetLang);
      fd.append('session_id', sessionId);
      fd.append('use_context', mode === 'context' ? useContext : false);

      if (file) {
        fd.append(mode === 'audio' ? 'audio' : 'video', file);
      } else {
        fd.append('text', cur.sourceText);
      }

      const res  = await fetch(`${API_URL}/translate`, { method:'POST', body:fd });
      const data = await res.json();

      // Update THIS mode's state only
      setModeStates(prev => ({
        ...prev,
        [mode]: {
          ...prev[mode],
          sourceText:    file ? (data.original || '') : prev[mode].sourceText,
          translatedText: data.translated || '',
          emotion:       data.emotion || null,
          perf:          data.performance || null,
          ctxInfluence:  data.context_used ? (data.context_sentences?.length||0)/3 : 0,
          context:       (mode==='context' && data.context_used)
                           ? (data.context_sentences||[])
                           : prev[mode].context,
        }
      }));

      setAnim(true); setVW(0);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleFile = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const url = URL.createObjectURL(file);
    setModeStates(prev => ({
      ...prev,
      [mode]: { ...prev[mode], mediaURL:url, mediaType:mode, fileName:file.name }
    }));
    handleTranslate(file);
  };

  const handleRefresh = async () => {
    if (!window.confirm('Clear all translations and start fresh?')) return;
    const fd = new FormData();
    fd.append('session_id', sessionId);
    await fetch(`${API_URL}/session/clear`, { method:'POST', body:fd }).catch(()=>{});
    // Reset ALL mode states
    setModeStates({
      text:    { ...EMPTY_MODE_STATE },
      context: { ...EMPTY_MODE_STATE },
      audio:   { ...EMPTY_MODE_STATE },
      video:   { ...EMPTY_MODE_STATE },
      emotion: { ...EMPTY_MODE_STATE },
    });
    setHistory([]); setShowH(false);
  };

  const loadHistory = async () => {
    try {
      const res  = await fetch(`${API_URL}/session/${sessionId}/history?limit=20`);
      const data = await res.json();
      if (data.history?.length > 0) { setHistory(data.history); setShowH(true); }
      else alert('No history yet. Start translating!');
    } catch { alert('Failed to load history'); }
  };

  const currentMode = MODES.find(m => m.id === mode);
  const words = cur.translatedText.split(' ');

  return (
    <div className="app">
      <div className="bg-grid" />
      <div className={`bg-glow glow-${currentMode.color}`} />

      <div className="wrap">
        {/* ── HEADER ── */}
        <header className="header">
          <div className="header-left">
            <div className={`logo-box logo-${currentMode.color}`}>
              <Languages size={20} />
            </div>
            <div>
              <h1 className="logo-title">LinguaContext</h1>
              <p className="logo-sub">Context-Aware Neural Translation</p>
            </div>
          </div>
          <div className="header-right">
            <div className="session-pill">
              <span className="session-live" />
              <span>{sessionId?.slice(0,16)}…</span>
            </div>
            <button onClick={loadHistory} className="hdr-btn">
              <History size={14}/> History
            </button>
            <button onClick={handleRefresh} className="hdr-btn hdr-btn-red">
              <RefreshCw size={14}/> Reset
            </button>
          </div>
        </header>

        {/* ── MODE TABS ── */}
        <div className="tabs">
          {MODES.map(m => {
            const Icon = m.icon;
            const active = mode === m.id;
            return (
              <button
                key={m.id}
                onClick={() => setMode(m.id)}
                className={`tab tab-${m.color} ${active ? 'tab-active' : ''}`}
              >
                <Icon size={15} />
                <span className="tab-main">{m.label}</span>
                <span className="tab-sub">{m.sub}</span>
              </button>
            );
          })}
        </div>

        {/* ── MAIN GRID ── */}
        <div className="grid">

          {/* LEFT — Input */}
          <div className={`card card-${currentMode.color}`}>
            <div className="card-top">
              <span className={`card-badge badge-${currentMode.color}`}>Source</span>
              <LangSelect value={sourceLang} onChange={setSource} color={currentMode.color} />
            </div>

            {mode === 'audio' || mode === 'video' ? (
              <FileZone
                mode={mode}
                mediaURL={cur.mediaURL}
                mediaType={cur.mediaType}
                fileName={cur.fileName}
                fileRef={fileRef}
                onFile={handleFile}
                onClear={() => {
                  setModeStates(prev => ({
                    ...prev,
                    [mode]: { ...prev[mode], mediaURL:null, mediaType:null, fileName:null }
                  }));
                  if (fileRef.current) fileRef.current.value = '';
                }}
                color={currentMode.color}
              />
            ) : (
              <textarea
                className={`textarea textarea-${currentMode.color}`}
                value={cur.sourceText}
                onChange={e => setModeField('sourceText', e.target.value)}
                placeholder="Enter text to translate…"
                onKeyDown={e => { if (e.key==='Enter' && e.ctrlKey) handleTranslate(); }}
              />
            )}

            {mode === 'context' && (
              <label className="ctx-toggle">
                <input
                  type="checkbox"
                  checked={useContext}
                  onChange={e => setUseCtx(e.target.checked)}
                  className="ctx-cb"
                />
                <span className="ctx-track" />
                <span className="ctx-label">Use conversation context</span>
              </label>
            )}

            <button
              className={`translate-btn btn-${currentMode.color}`}
              onClick={() => handleTranslate()}
              disabled={loading || (!cur.sourceText && mode!=='audio' && mode!=='video')}
            >
              {loading
                ? <><Loader2 size={17} className="spin"/> Processing…</>
                : <><Zap size={17}/> Translate</>
              }
            </button>

            {/* Transcribed text */}
            {(mode==='audio'||mode==='video') && cur.sourceText && (
              <div className="transcribed">
                <span className={`transcribed-label label-${currentMode.color}`}>
                  Transcribed Text
                </span>
                <p>{cur.sourceText}</p>
              </div>
            )}

            {/* Context list */}
            {mode==='context' && (
              <div className="ctx-panel">
                <div className="ctx-head">
                  <span>Context ({cur.context.length})</span>
                  <button className="xs-btn" onClick={() => setModeField('context', [])}>Clear</button>
                </div>
                {cur.context.length===0
                  ? <p className="muted">No context yet — start translating!</p>
                  : cur.context.map((c,i) => <div key={i} className="ctx-item">{c}</div>)
                }
              </div>
            )}
          </div>

          {/* RIGHT — Output */}
          <div className={`card card-${currentMode.color}`}>
            <div className="card-top">
              <span className={`card-badge badge-${currentMode.color}`}>Translation</span>
              <LangSelect value={targetLang} onChange={setTarget} color={currentMode.color} />
            </div>

            {/* Media player on output side */}
            {(mode==='audio'||mode==='video') && cur.mediaURL && (
              <div className={`media-out media-out-${currentMode.color}`}>
                <div className="media-out-head">
                  <span>{mode==='video'?'🎬':'🎤'} {mode==='video'?'Video':'Audio'} Source</span>
                  <span className="media-fname">{cur.fileName}</span>
                </div>
                {mode==='video'
                  ? <video src={cur.mediaURL} controls className="media-player-v"/>
                  : <audio src={cur.mediaURL} controls className="media-player-a"/>
                }
              </div>
            )}

            <div className={`output-box output-${currentMode.color}`}>
              {cur.translatedText ? (
                <div className="words">
                  {words.slice(0, visibleWords).map((w,i) => (
                    <span key={i} className={`word word-${currentMode.color}`}>{w} </span>
                  ))}
                  {animating && visibleWords < words.length && (
                    <span className={`caret caret-${currentMode.color}`}/>
                  )}
                </div>
              ) : (
                <div className="output-empty">
                  <ArrowRight size={28} className="output-empty-icon"/>
                  <p>Translation will appear here…</p>
                </div>
              )}
            </div>

            {/* Context influence */}
            {cur.ctxInfluence > 0 && (
              <div className="influence">
                <div className="influence-head">
                  <span>Context Influence</span>
                  <strong>{Math.round(cur.ctxInfluence*100)}%</strong>
                </div>
                <div className="influence-track">
                  <div className={`influence-fill fill-purple`}
                    style={{width:`${cur.ctxInfluence*100}%`}}>
                    <div className="shimmer"/>
                  </div>
                </div>
              </div>
            )}

            {/* Performance */}
            {cur.perf && <PerfCard perf={cur.perf} color={currentMode.color}/>}

            {/* Emotion */}
            {cur.emotion && <EmotionCard emotion={cur.emotion}/>}
          </div>
        </div>

        <footer className="footer">
          ⚡ MyMemory · LibreTranslate · Lingva · NLLB-600M fallback &nbsp;|&nbsp;
          Whisper Tiny · DistilRoBERTa Emotion
        </footer>
      </div>

      {/* History Modal */}
      {showHistory && (
        <div className="overlay" onClick={() => setShowH(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div className="modal-head">
              <h2>Translation History</h2>
              <button className="modal-close" onClick={() => setShowH(false)}>
                <X size={15}/>
              </button>
            </div>
            <div className="modal-body">
              {history.length===0
                ? <p className="muted" style={{textAlign:'center',padding:'2rem'}}>No history yet</p>
                : [...history].reverse().map((item,i) => (
                  <div key={i} className="hist-item">
                    <div className="hist-top">
                      <span className="hist-num">#{history.length-i}</span>
                      <span className="hist-time">
                        {new Date(item.timestamp).toLocaleTimeString()}
                      </span>
                      <span className="hist-langs">
                        {item.source_lang} → {item.target_lang}
                      </span>
                      {item.emotion && (
                        <span className="hist-emo"
                          style={{color:EMOTION_COLORS[item.emotion.emotion]||'#94a3b8'}}>
                          {EMOTION_ICONS[item.emotion.emotion]||'😐'} {item.emotion.emotion}
                        </span>
                      )}
                    </div>
                    <div className="hist-orig">{item.original}</div>
                    <div className="hist-trans">{item.translated}</div>
                  </div>
                ))
              }
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Sub-components ──────────────────────────────────────────

function LangSelect({ value, onChange, color }) {
  return (
    <div className="lang-wrap">
      <select
        className={`lang-sel lang-sel-${color}`}
        value={value}
        onChange={e => onChange(e.target.value)}
      >
        {LANGUAGES.map(l => (
          <option key={l} value={l}>
            {l.charAt(0).toUpperCase()+l.slice(1)}
          </option>
        ))}
      </select>
      <ChevronDown size={12} className="lang-chev"/>
    </div>
  );
}

function FileZone({ mode, mediaURL, mediaType, fileName, fileRef, onFile, onClear, color }) {
  return (
    <div className="file-zone">
      {mediaURL ? (
        <div className={`media-wrap media-wrap-${color}`}>
          <div className="media-top">
            <span className="media-name">📁 {fileName}</span>
            <button className="xs-btn xs-btn-red" onClick={onClear}>
              <X size={11}/> Remove
            </button>
          </div>
          {mediaType==='video'
            ? <video src={mediaURL} controls className="media-player-v"/>
            : <audio src={mediaURL} controls className="media-player-a"/>
          }
          <button className="reupload" onClick={() => fileRef.current?.click()}>
            <Upload size={12}/> Upload different file
          </button>
        </div>
      ) : (
        <button className={`upload-btn upload-${color}`}
          onClick={() => fileRef.current?.click()}>
          <Upload size={30} className="upload-icon"/>
          <span className="upload-main">
            Click to upload {mode} file
          </span>
          <span className="upload-sub">
            {mode==='audio' ? 'MP3, WAV, M4A, OGG' : 'MP4, MOV, AVI, WebM'}
          </span>
        </button>
      )}
      <input
        ref={fileRef}
        type="file"
        accept={mode==='audio' ? 'audio/*' : 'video/*'}
        onChange={onFile}
        style={{display:'none'}}
      />
    </div>
  );
}

function PerfCard({ perf, color }) {
  const method = perf.method || 'api';
  const methodColor = {
    cache:        '#22c55e',
    mymemory:     '#3b82f6',
    libretranslate:'#a855f7',
    lingva:       '#f59e0b',
    local_nllb:   '#ef4444',
  }[method] || '#94a3b8';

  return (
    <div className={`perf-card perf-${color}`}>
      <div className="perf-head">
        <Activity size={13}/>
        <span>Performance</span>
        <span className="method-badge" style={{background:`${methodColor}22`,color:methodColor,border:`1px solid ${methodColor}44`}}>
          {method}
        </span>
      </div>
      <div className="perf-grid">
        {perf.transcription_ms > 0 && (
          <div className="perf-item">
            <span>Transcription</span>
            <strong>{perf.transcription_ms.toFixed(0)}ms</strong>
          </div>
        )}
        <div className="perf-item">
          <span>Translation</span>
          <strong>{perf.translation_ms.toFixed(0)}ms</strong>
        </div>
        <div className="perf-item">
          <span>Emotion</span>
          <strong>{perf.emotion_detection_ms?.toFixed(0)||0}ms</strong>
        </div>
        <div className="perf-item perf-total">
          <span>Total</span>
          <strong>{perf.total_ms.toFixed(0)}ms</strong>
        </div>
      </div>
    </div>
  );
}

function EmotionCard({ emotion }) {
  const EMOS = ['joy','sadness','anger','fear','surprise','neutral'];
  const scores = emotion.scores || {};
  const domColor = EMOTION_COLORS[emotion.emotion?.toLowerCase()] || '#94a3b8';
  const needle = (emotion.confidence * 180) - 90;

  return (
    <div className="emo-card">
      <div className="emo-head">
        <span className="emo-big-icon">
          {EMOTION_ICONS[emotion.emotion?.toLowerCase()]||'😐'}
        </span>
        <div>
          <div className="emo-name" style={{color:domColor}}>
            {emotion.emotion?.toUpperCase()}
          </div>
          <div className="emo-conf">
            {(emotion.confidence*100).toFixed(1)}% confidence
          </div>
        </div>
      </div>

      <div className="gauge-wrap">
        <svg viewBox="0 0 200 105" className="gauge-svg">
          <path d="M 20 100 A 80 80 0 0 1 180 100"
            fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="14" strokeLinecap="round"/>
          <path d="M 20 100 A 80 80 0 0 1 180 100"
            fill="none" stroke={domColor} strokeWidth="14" strokeLinecap="round"
            strokeDasharray={`${emotion.confidence*251.2} 251.2`}
            style={{filter:`drop-shadow(0 0 8px ${domColor})`,transition:'stroke-dasharray .6s'}}/>
          <g transform={`rotate(${needle},100,100)`}>
            <line x1="100" y1="100" x2="100" y2="32"
              stroke="white" strokeWidth="2.5" strokeLinecap="round"/>
            <circle cx="100" cy="100" r="5" fill="white"/>
          </g>
          <text x="16" y="100" fontSize="10" fill="rgba(255,255,255,0.35)">0%</text>
          <text x="174" y="100" fontSize="10" fill="rgba(255,255,255,0.35)">100%</text>
        </svg>
      </div>

      <div className="emo-bars">
        {EMOS.map(em => {
          const sc = scores[em]||0;
          const col = EMOTION_COLORS[em];
          const active = em === emotion.emotion?.toLowerCase();
          return (
            <div key={em} className={`emo-row ${active?'emo-row-active':''}`}>
              <span className="emo-lbl">{EMOTION_ICONS[em]} {em}</span>
              <div className="emo-track">
                <div className="emo-fill" style={{
                  width:`${sc*100}%`, background:col,
                  boxShadow: active?`0 0 10px ${col}`:''
                }}/>
              </div>
              <span className="emo-pct" style={{color:active?col:undefined}}>
                {(sc*100).toFixed(0)}%
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}